import { NextRequest, NextResponse } from 'next/server';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || '';

/**
 * GET /api/admin/releases/active - 获取当前活跃的 Release
 * Query params: tenant_id, site_id
 */
export async function GET(req: NextRequest) {
  const searchParams = req.nextUrl.searchParams;
  const tenantId = searchParams.get('tenant_id') || 'yantian';
  const siteId = searchParams.get('site_id') || 'yantian-main';
  const url = `${CORE_BACKEND_URL}/api/v1/releases/active?tenant_id=${tenantId}&site_id=${siteId}`;

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'X-Internal-API-Key': INTERNAL_API_KEY,
      },
    });

    // 如果没有活跃的 release，返回 null
    if (response.status === 404) {
      return NextResponse.json(null, { status: 200 });
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
