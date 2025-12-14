import { NextRequest, NextResponse } from 'next/server';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || '';

/**
 * POST /api/admin/alerts/evaluate - 手动触发告警评估
 * Query params: tenant_id, site_id
 */
export async function POST(req: NextRequest) {
  const searchParams = req.nextUrl.searchParams;
  const tenantId = searchParams.get('tenant_id') || 'yantian';
  const siteId = searchParams.get('site_id') || '';
  
  let url = `${CORE_BACKEND_URL}/api/v1/alerts/evaluate-persist?tenant_id=${tenantId}`;
  if (siteId) {
    url += `&site_id=${siteId}`;
  }

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-API-Key': INTERNAL_API_KEY,
        'X-Operator': 'admin_console',
      },
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || 'Proxy error' },
      { status: 500 }
    );
  }
}
