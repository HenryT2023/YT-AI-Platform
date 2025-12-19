import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/achievements - 获取成就列表
 * POST /api/admin/achievements - 创建成就
 */
export async function GET(req: NextRequest) {
  return proxyRequest('/api/v1/achievements', {
    searchParams: req.nextUrl.searchParams,
  });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  return proxyRequest('/api/v1/achievements', {
    method: 'POST',
    body,
  });
}
