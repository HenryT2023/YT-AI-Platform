import { NextRequest, NextResponse } from 'next/server';

// Cookie 名称
const ACCESS_COOKIE = 'yt_admin_access';
const REFRESH_COOKIE = 'yt_admin_refresh';

// 需要认证的路径
const PROTECTED_PATHS = [
  '/admin',
  '/dashboard',
  '/npcs',
  '/scenes',
  '/quests',
  '/visitors',
  '/settings',
];

// 公开路径（不需要认证）
const PUBLIC_PATHS = [
  '/login',
  '/api/auth/login',
  '/api/auth/refresh',
];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // 检查是否是公开路径
  if (PUBLIC_PATHS.some(path => pathname.startsWith(path))) {
    return NextResponse.next();
  }

  // 检查是否是需要保护的路径
  const isProtectedPath = PROTECTED_PATHS.some(path => pathname.startsWith(path));
  
  if (!isProtectedPath) {
    return NextResponse.next();
  }

  // 获取 tokens
  const accessToken = request.cookies.get(ACCESS_COOKIE)?.value;
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;

  // 没有任何 token，重定向到登录页
  if (!accessToken && !refreshToken) {
    const loginUrl = new URL('/login', request.url);
    loginUrl.searchParams.set('redirect', pathname);
    return NextResponse.redirect(loginUrl);
  }

  // 有 access token 或 refresh token，继续请求
  // 如果 access token 过期，代理层会自动尝试 refresh
  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public files (public folder)
     */
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};
