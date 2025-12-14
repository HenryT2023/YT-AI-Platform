import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';
const COOKIE_NAME = 'yt_admin_token';
const COOKIE_MAX_AGE = 60 * 60 * 24 * 7; // 7 days

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { username, password } = body;

    if (!username || !password) {
      return NextResponse.json(
        { error: '用户名和密码不能为空' },
        { status: 400 }
      );
    }

    // 转发到 core-backend
    const response = await fetch(`${CORE_BACKEND_URL}/api/v1/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || '登录失败' },
        { status: response.status }
      );
    }

    // 设置 HttpOnly cookie
    const cookieStore = await cookies();
    cookieStore.set(COOKIE_NAME, data.access_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: COOKIE_MAX_AGE,
      path: '/',
    });

    // 返回用户信息（不包含 token）
    return NextResponse.json({
      success: true,
      user: data.user,
    });
  } catch (error: any) {
    console.error('Login error:', error);
    return NextResponse.json(
      { error: '登录服务暂时不可用' },
      { status: 500 }
    );
  }
}
