import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * POST /api/admin/achievements/[id]/grant - 手动颁发成就给用户
 */
export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await req.json();
  return proxyRequest(`/api/v1/achievements/${params.id}/grant`, {
    method: 'POST',
    body,
  });
}
