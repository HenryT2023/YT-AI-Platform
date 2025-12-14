import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  getAccessCookieOptions,
  getRefreshCookieOptions,
} from '@/lib/cookie-config';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';

export async function POST() {
  const cookieStore = await cookies();
  
  // 获取 refresh token
  const refreshToken = cookieStore.get(REFRESH_COOKIE)?.value;
  
  if (!refreshToken) {
    return NextResponse.json(
      { error: '未找到刷新令牌' },
      { status: 401 }
    );
  }
  
  try {
    // 调用后端 refresh 端点
    const response = await fetch(`${CORE_BACKEND_URL}/api/v1/auth/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    
    const data = await response.json();
    
    if (!response.ok) {
      // 刷新失败，清除 cookies
      cookieStore.delete(ACCESS_COOKIE);
      cookieStore.delete(REFRESH_COOKIE);
      
      return NextResponse.json(
        { error: data.detail || '刷新令牌失败' },
        { status: response.status }
      );
    }
    
    // 更新 cookies（使用环境化配置）
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
    
    return NextResponse.json({ success: true });
  } catch (error: any) {
    console.error('Refresh error:', error);
    return NextResponse.json(
      { error: '刷新服务暂时不可用' },
      { status: 500 }
    );
  }
}
