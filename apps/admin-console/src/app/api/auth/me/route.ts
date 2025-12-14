import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';
const COOKIE_NAME = 'yt_admin_token';

export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(COOKIE_NAME)?.value;

  if (!token) {
    return NextResponse.json(
      { error: '未登录' },
      { status: 401 }
    );
  }

  try {
    const response = await fetch(`${CORE_BACKEND_URL}/api/v1/auth/me`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      // Token 无效，清除 cookie
      if (response.status === 401) {
        cookieStore.delete(COOKIE_NAME);
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
