import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/achievements/[id] - 获取成就详情
 * PATCH /api/admin/achievements/[id] - 更新成就
 * DELETE /api/admin/achievements/[id] - 删除成就
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/achievements/${params.id}`);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await req.json();
  return proxyRequest(`/api/v1/achievements/${params.id}`, {
    method: 'PATCH',
    body,
  });
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/achievements/${params.id}`, {
    method: 'DELETE',
  });
}
