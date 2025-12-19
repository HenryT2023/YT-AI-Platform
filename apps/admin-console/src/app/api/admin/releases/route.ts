import { NextRequest, NextResponse } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/releases - 获取 Release 列表
 * v0.2.4: tenant/site 由 proxyRequest 从 Header 注入
 */
export async function GET(req: NextRequest) {
  return proxyRequest('/api/v1/releases', { searchParams: req.nextUrl.searchParams });
}

/**
 * POST /api/admin/releases - 创建新 Release
 * v0.2.4: tenant/site 由 proxyRequest 从 Header 注入
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    if (!body.created_by) {
      body.created_by = 'admin_console';
    }
    return proxyRequest('/api/v1/releases', { method: 'POST', body });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || 'Proxy error' },
      { status: 500 }
    );
  }
}
