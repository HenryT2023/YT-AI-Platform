import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/visitor-profiles - 获取游客画像列表
 * POST /api/admin/visitor-profiles - 创建游客画像
 */
export async function GET(req: NextRequest) {
  return proxyRequest('/api/v1/visitor-profiles', {
    searchParams: req.nextUrl.searchParams,
  });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  return proxyRequest('/api/v1/visitor-profiles', {
    method: 'POST',
    body,
  });
}
