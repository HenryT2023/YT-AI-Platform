import { NextRequest, NextResponse } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

export async function GET(req: NextRequest) {
  try {
    const response = await proxyRequest('/api/v1/npcs', {
      method: 'GET',
      searchParams: req.nextUrl.searchParams,
    });

    if (response.status === 401) {
      return NextResponse.json({ error: '登录已过期' }, { status: 401 });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || 'Proxy error' },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const response = await proxyRequest('/api/v1/npcs', {
      method: 'POST',
      body,
    });

    if (response.status === 401) {
      return NextResponse.json({ error: '登录已过期' }, { status: 401 });
    }

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || 'Proxy error' },
      { status: 500 }
    );
  }
}
