import { NextRequest, NextResponse } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const comment = req.nextUrl.searchParams.get('comment');
    const url = comment 
      ? `/api/v1/admin/quest-submissions/${id}/approve?comment=${encodeURIComponent(comment)}`
      : `/api/v1/admin/quest-submissions/${id}/approve`;
    const response = await proxyRequest(url, {
      method: 'POST',
    });
    if (response.status === 401) return NextResponse.json({ error: '登录已过期' }, { status: 401 });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    return NextResponse.json({ error: error.message || 'Proxy error' }, { status: 500 });
  }
}
