import { cookies } from 'next/headers';
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  getAccessCookieOptions,
  getRefreshCookieOptions,
} from './cookie-config';

// 重新导出 cookie 常量
export { ACCESS_COOKIE, REFRESH_COOKIE };

// 向后兼容
export const COOKIE_NAME = ACCESS_COOKIE;

export const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';
export const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || '';

// Tenant/Site Scope 配置
// 灰度期使用环境变量配置默认值，后续可扩展为站点切换器
export const DEFAULT_TENANT_ID = process.env.DEFAULT_TENANT_ID || 'yantian';
export const DEFAULT_SITE_ID = process.env.DEFAULT_SITE_ID || 'yantian-main';

// Tenant/Site Cookie 名称（用于站点切换器）
export const TENANT_COOKIE = 'yt_admin_tenant';
export const SITE_COOKIE = 'yt_admin_site';

/**
 * 获取当前用户的 access token
 */
export async function getAuthToken(): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get(ACCESS_COOKIE)?.value || null;
}

/**
 * 获取 refresh token
 */
export async function getRefreshToken(): Promise<string | null> {
  const cookieStore = await cookies();
  return cookieStore.get(REFRESH_COOKIE)?.value || null;
}

/**
 * 获取当前 tenant_id
 * 优先读取 cookie，没有则用环境变量默认值
 */
export async function getTenantId(): Promise<string> {
  const cookieStore = await cookies();
  return cookieStore.get(TENANT_COOKIE)?.value || DEFAULT_TENANT_ID;
}

/**
 * 获取当前 site_id
 * 优先读取 cookie，没有则用环境变量默认值
 */
export async function getSiteId(): Promise<string> {
  const cookieStore = await cookies();
  return cookieStore.get(SITE_COOKIE)?.value || DEFAULT_SITE_ID;
}

/**
 * 构建带认证和 scope 的请求头
 * 自动注入 X-Tenant-ID 和 X-Site-ID
 */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const token = await getAuthToken();
  const tenantId = await getTenantId();
  const siteId = await getSiteId();
  
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Tenant-ID': tenantId,
    'X-Site-ID': siteId,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  } else if (INTERNAL_API_KEY) {
    // Fallback to internal API key for server-side calls
    headers['X-Internal-API-Key'] = INTERNAL_API_KEY;
  }

  return headers;
}

// ============================================================
// Refresh Token 并发互斥锁
// ============================================================

/**
 * 全局 refresh 锁
 * 
 * 用于防止多个并发请求同时触发 refresh，导致：
 * 1. 多次 rotate 使前面的 refresh token 失效
 * 2. 竞争条件导致部分请求使用过期的 token
 * 
 * 实现：
 * - 同一时刻只允许一个 refresh 请求在飞
 * - 后续请求等待同一个 promise 结果
 */
let refreshPromise: Promise<boolean> | null = null;
let refreshLockTime: number = 0;
const REFRESH_LOCK_TIMEOUT = 10000; // 10 秒超时

/**
 * 带互斥锁的 refresh token
 * 
 * 确保同一时刻只有一个 refresh 请求在执行
 */
async function refreshTokenWithMutex(): Promise<boolean> {
  const now = Date.now();
  
  // 检查是否有正在进行的 refresh 请求
  if (refreshPromise && (now - refreshLockTime) < REFRESH_LOCK_TIMEOUT) {
    // 等待现有的 refresh 完成
    console.log('[auth-utils] Waiting for existing refresh request...');
    return refreshPromise;
  }
  
  // 获取锁并执行 refresh
  refreshLockTime = now;
  refreshPromise = doRefreshToken();
  
  try {
    const result = await refreshPromise;
    return result;
  } finally {
    // 释放锁
    refreshPromise = null;
  }
}

/**
 * 实际执行 refresh token 的函数
 */
async function doRefreshToken(): Promise<boolean> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) {
    console.log('[auth-utils] No refresh token available');
    return false;
  }

  try {
    console.log('[auth-utils] Executing refresh token request...');
    
    const response = await fetch(`${CORE_BACKEND_URL}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      console.log('[auth-utils] Refresh failed:', response.status);
      return false;
    }

    const data = await response.json();
    
    // 更新 cookies（使用环境化配置）
    const cookieStore = await cookies();
    
    cookieStore.set(
      ACCESS_COOKIE, 
      data.access_token, 
      getAccessCookieOptions(data.access_expires_in)
    );
    
    cookieStore.set(
      REFRESH_COOKIE, 
      data.refresh_token, 
      getRefreshCookieOptions(data.refresh_expires_in)
    );

    console.log('[auth-utils] Refresh successful');
    return true;
  } catch (error) {
    console.error('[auth-utils] Token refresh failed:', error);
    return false;
  }
}

/**
 * 尝试刷新 token（带互斥锁）
 * 返回是否成功
 */
export async function tryRefreshToken(): Promise<boolean> {
  return refreshTokenWithMutex();
}

/**
 * 代理请求到 core-backend
 * 支持 401 自动重试（先 refresh 再重试一次，带互斥锁）
 */
export async function proxyRequest(
  path: string,
  options: {
    method?: string;
    body?: any;
    searchParams?: URLSearchParams;
  } = {}
): Promise<Response> {
  const { method = 'GET', body, searchParams } = options;
  
  let url = `${CORE_BACKEND_URL}${path}`;
  if (searchParams && searchParams.toString()) {
    url += `?${searchParams.toString()}`;
  }

  // 第一次请求
  let headers = await getAuthHeaders();
  let fetchOptions: RequestInit = {
    method,
    headers,
  };

  if (body && method !== 'GET') {
    fetchOptions.body = JSON.stringify(body);
  }

  let response = await fetch(url, fetchOptions);

  // 如果返回 401，尝试 refresh 并重试一次（带互斥锁）
  if (response.status === 401) {
    console.log(`[auth-utils] Got 401 for ${method} ${path}, attempting refresh...`);
    
    const refreshed = await tryRefreshToken();
    
    if (refreshed) {
      // 重新获取 headers（包含新的 access token）
      headers = await getAuthHeaders();
      fetchOptions = {
        method,
        headers,
      };
      
      if (body && method !== 'GET') {
        fetchOptions.body = JSON.stringify(body);
      }
      
      // 重试请求（仅一次，防止循环）
      console.log(`[auth-utils] Retrying ${method} ${path} with new token...`);
      response = await fetch(url, fetchOptions);
    } else {
      console.log(`[auth-utils] Refresh failed, returning 401`);
    }
  }

  return response;
}
