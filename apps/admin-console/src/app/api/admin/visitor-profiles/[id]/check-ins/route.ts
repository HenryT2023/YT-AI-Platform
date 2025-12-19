import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/visitor-profiles/[id]/check-ins - 获取打卡记录列表
 * POST /api/admin/visitor-profiles/[id]/check-ins - 创建打卡记录
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}/check-ins`, {
    searchParams: req.nextUrl.searchParams,
  });
}

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await req.json();
  return proxyRequest(`/api/v1/visitor-profiles/${params.id}/check-ins`, {
    method: 'POST',
    body,
  });
}
