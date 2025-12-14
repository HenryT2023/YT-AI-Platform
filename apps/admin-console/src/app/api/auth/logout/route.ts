import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const COOKIE_NAME = 'yt_admin_token';

export async function POST() {
  const cookieStore = await cookies();
  
  // 清除 cookie
  cookieStore.delete(COOKIE_NAME);

  return NextResponse.json({ success: true });
}
