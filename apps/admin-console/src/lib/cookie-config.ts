/**
 * Cookie 安全配置
 * 
 * 根据环境设置 Cookie 安全属性：
 * - development: secure=false, sameSite='lax'
 * - production: secure=true, sameSite='strict'
 * 
 * 为什么 production 使用 sameSite='strict'：
 * - 防止 CSRF 攻击，cookie 不会在跨站请求中发送
 * - admin-console 是内部管理系统，不需要跨站访问
 * - 如果需要支持 OAuth 回调等场景，可改为 'lax'
 */

// Cookie 名称常量
export const ACCESS_COOKIE = 'yt_admin_access';
export const REFRESH_COOKIE = 'yt_admin_refresh';

// Tenant/Site Scope Cookie 名称
export const TENANT_COOKIE = 'yt_admin_tenant';
export const SITE_COOKIE = 'yt_admin_site';

// Cookie 有效期（秒）
export const ACCESS_MAX_AGE = 60 * 15; // 15 分钟
export const REFRESH_MAX_AGE = 60 * 60 * 24 * 7; // 7 天

// 判断是否为生产环境
export const isProduction = process.env.NODE_ENV === 'production';

// Cookie 安全配置
export interface CookieSecurityOptions {
  httpOnly: boolean;
  secure: boolean;
  sameSite: 'strict' | 'lax' | 'none';
  path: string;
}

/**
 * 获取 Cookie 安全配置
 */
export function getCookieSecurityOptions(): CookieSecurityOptions {
  return {
    httpOnly: true,
    secure: isProduction,
    sameSite: isProduction ? 'strict' : 'lax',
    path: '/',
  };
}

/**
 * 获取 Access Token Cookie 配置
 */
export function getAccessCookieOptions(expiresIn?: number) {
  return {
    ...getCookieSecurityOptions(),
    maxAge: expiresIn || ACCESS_MAX_AGE,
  };
}

/**
 * 获取 Refresh Token Cookie 配置
 */
export function getRefreshCookieOptions(expiresIn?: number) {
  return {
    ...getCookieSecurityOptions(),
    maxAge: expiresIn || REFRESH_MAX_AGE,
  };
}
