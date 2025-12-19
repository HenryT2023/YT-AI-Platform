import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/visitor-profiles/[id]/interactions - 获取交互记录列表
 * POST /api/admin/visitor-profiles/[id]/interactions - 创建/更新交互记录
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}/interactions`, {
    searchParams: req.nextUrl.searchParams,
  });
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await req.json();
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}/interactions`, {
    method: 'POST',
    body,
  });
}
