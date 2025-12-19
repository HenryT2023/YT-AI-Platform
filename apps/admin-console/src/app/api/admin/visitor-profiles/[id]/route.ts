import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/visitor-profiles/[id] - 获取游客画像详情
 * PATCH /api/admin/visitor-profiles/[id] - 更新游客画像
 * DELETE /api/admin/visitor-profiles/[id] - 删除游客画像
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}`);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await req.json();
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}`, {
    method: 'PATCH',
    body,
  });
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}`, {
    method: 'DELETE',
  });
}
