import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { ACCESS_COOKIE, REFRESH_COOKIE } from '@/lib/cookie-config';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const accessToken = cookieStore.get(ACCESS_COOKIE)?.value;

  if (!accessToken) {
    // 没有 access token，检查是否有 refresh token
    const refreshToken = cookieStore.get(REFRESH_COOKIE)?.value;
    if (refreshToken) {
      // 有 refresh token，返回特殊状态让前端触发 refresh
      return NextResponse.json(
        { error: '访问令牌已过期', needRefresh: true },
        { status: 401 }
      );
    }
    return NextResponse.json(
      { error: '未登录' },
      { status: 401 }
    );
  }

  try {
    const response = await fetch(`${CORE_BACKEND_URL}/api/v1/auth/me`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
      },
    });

    if (!response.ok) {
      if (response.status === 401) {
        // Access token 无效，检查是否有 refresh token
        const refreshToken = cookieStore.get(REFRESH_COOKIE)?.value;
        if (refreshToken) {
          return NextResponse.json(
            { error: '访问令牌已过期', needRefresh: true },
            { status: 401 }
          );
        }
        // 没有 refresh token，清除所有 cookies
        cookieStore.delete(ACCESS_COOKIE);
      }
      return NextResponse.json(
        { error: '登录已过期' },
        { status: 401 }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Get user info error:', error);
    return NextResponse.json(
      { error: '获取用户信息失败' },
      { status: 500 }
    );
  }
}
