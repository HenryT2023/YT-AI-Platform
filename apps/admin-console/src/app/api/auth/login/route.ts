import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  getAccessCookieOptions,
  getRefreshCookieOptions,
} from '@/lib/cookie-config';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';

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

    // 转发到 core-backend（包含客户端 IP）
    const clientIp = req.headers.get('x-forwarded-for')?.split(',')[0] || 
                     req.headers.get('x-real-ip') || 
                     'unknown';
    
    const response = await fetch(`${CORE_BACKEND_URL}/api/v1/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Forwarded-For': clientIp,
      },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();

    if (!response.ok) {
      // 处理锁定响应
      if (response.status === 429 && data.detail?.locked) {
        return NextResponse.json(
          { 
            error: data.detail.message,
            locked: true,
            remaining_seconds: data.detail.remaining_seconds,
          },
          { status: 429 }
        );
      }
      return NextResponse.json(
        { error: typeof data.detail === 'string' ? data.detail : '登录失败' },
        { status: response.status }
      );
    }

    // 设置 HttpOnly cookies（使用环境化配置）
    const cookieStore = await cookies();
    
    // Access token cookie
    cookieStore.set(
      ACCESS_COOKIE, 
      data.access_token, 
      getAccessCookieOptions(data.access_expires_in)
    );
    
    // Refresh token cookie
    cookieStore.set(
      REFRESH_COOKIE, 
      data.refresh_token, 
      getRefreshCookieOptions(data.refresh_expires_in)
    );

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
