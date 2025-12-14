import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { ACCESS_COOKIE, REFRESH_COOKIE } from '@/lib/cookie-config';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';

export async function POST() {
  const cookieStore = await cookies();
  
  // 获取 refresh token
  const refreshToken = cookieStore.get(REFRESH_COOKIE)?.value;
  
  // 调用后端 logout 撤销 refresh token
  if (refreshToken) {
    try {
      await fetch(`${CORE_BACKEND_URL}/api/v1/auth/logout`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch (error) {
      // 即使后端调用失败，也继续清除本地 cookie
      console.error('Logout backend call failed:', error);
    }
  }
  
  // 清除 cookies
  cookieStore.delete(ACCESS_COOKIE);
  cookieStore.delete(REFRESH_COOKIE);

  return NextResponse.json({ success: true });
}
