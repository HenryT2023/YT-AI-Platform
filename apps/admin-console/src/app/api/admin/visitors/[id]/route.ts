import { NextRequest, NextResponse } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const response = await proxyRequest(`/api/v1/visitors/${params.id}`, { method: 'GET' });
    if (response.status === 401) return NextResponse.json({ error: '登录已过期' }, { status: 401 });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    return NextResponse.json({ error: error.message || 'Proxy error' }, { status: 500 });
  }
}
