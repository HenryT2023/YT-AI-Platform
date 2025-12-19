import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/farming-knowledge - 获取农耕知识列表
 * POST /api/admin/farming-knowledge - 创建农耕知识
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const params = searchParams.toString();
  return proxyRequest(`/api/v1/farming-knowledge${params ? `?${params}` : ''}`);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  return proxyRequest('/api/v1/farming-knowledge', {
    method: 'POST',
    body,
  });
}
