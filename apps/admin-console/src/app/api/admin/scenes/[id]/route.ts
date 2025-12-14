import { NextRequest, NextResponse } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const response = await proxyRequest(`/api/v1/scenes/${params.id}`, { method: 'GET' });
    if (response.status === 401) return NextResponse.json({ error: '登录已过期' }, { status: 401 });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    return NextResponse.json({ error: error.message || 'Proxy error' }, { status: 500 });
  }
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const body = await req.json();
    const response = await proxyRequest(`/api/v1/scenes/${params.id}`, { method: 'PATCH', body });
    if (response.status === 401) return NextResponse.json({ error: '登录已过期' }, { status: 401 });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    return NextResponse.json({ error: error.message || 'Proxy error' }, { status: 500 });
  }
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const response = await proxyRequest(`/api/v1/scenes/${params.id}`, { method: 'DELETE' });
    if (response.status === 401) return NextResponse.json({ error: '登录已过期' }, { status: 401 });
    if (response.status === 204) return new NextResponse(null, { status: 204 });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    return NextResponse.json({ error: error.message || 'Proxy error' }, { status: 500 });
  }
}
