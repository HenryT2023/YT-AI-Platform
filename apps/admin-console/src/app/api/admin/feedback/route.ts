import { NextRequest, NextResponse } from 'next/server';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || '';

async function proxyRequest(
  req: NextRequest,
  path: string,
  method: string = 'GET'
) {
  const url = `${CORE_BACKEND_URL}/api/v1${path}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Internal-API-Key': INTERNAL_API_KEY,
    'X-Operator': 'admin_console',
  };

  // 透传租户信息
  const tenantId = req.headers.get('X-Tenant-ID');
  const siteId = req.headers.get('X-Site-ID');
  if (tenantId) headers['X-Tenant-ID'] = tenantId;
  if (siteId) headers['X-Site-ID'] = siteId;

  const options: RequestInit = {
    method,
    headers,
  };

  if (method !== 'GET' && method !== 'HEAD') {
    try {
      const body = await req.json();
      options.body = JSON.stringify(body);
    } catch {
      // No body
    }
  }

  try {
    const response = await fetch(url, options);
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || 'Proxy error' },
      { status: 500 }
    );
  }
}

// GET /api/admin/feedback - 列表
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const queryString = searchParams.toString();
  const path = `/feedback${queryString ? `?${queryString}` : ''}`;
  return proxyRequest(req, path, 'GET');
}
