import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * PATCH /api/admin/visitor-profiles/[id]/tags/[tagId] - 更新游客标签
 * DELETE /api/admin/visitor-profiles/[id]/tags/[tagId] - 删除游客标签
 */
export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string; tagId: string } }
) {
  const body = await req.json();
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}/tags/${params.tagId}`, {
    method: 'PATCH',
    body,
  });
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string; tagId: string } }
) {
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}/tags/${params.tagId}`, {
    method: 'DELETE',
  });
}
