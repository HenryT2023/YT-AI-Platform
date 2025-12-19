import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/visitor-profiles/[id]/tags - 获取游客标签列表
 * POST /api/admin/visitor-profiles/[id]/tags - 添加游客标签
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}/tags`, {
    searchParams: req.nextUrl.searchParams,
  });
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await req.json();
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}/tags`, {
    method: 'POST',
    body,
  });
}
