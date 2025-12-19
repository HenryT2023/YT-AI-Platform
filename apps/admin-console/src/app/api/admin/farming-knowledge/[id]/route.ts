import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/farming-knowledge/[id] - 获取知识详情
 * PATCH /api/admin/farming-knowledge/[id] - 更新知识
 * DELETE /api/admin/farming-knowledge/[id] - 删除知识
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/farming-knowledge/${params.id}`);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await req.json();
  return proxyRequest(`/api/v1/farming-knowledge/${params.id}`, {
    method: 'PATCH',
    body,
  });
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/farming-knowledge/${params.id}`, {
    method: 'DELETE',
  });
}
