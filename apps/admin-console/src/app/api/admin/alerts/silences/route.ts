import { NextRequest, NextResponse } from 'next/server';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || '';

/**
 * GET /api/admin/alerts/silences - 获取静默规则列表
 * Query params: tenant_id, site_id, active_only
 */
export async function GET(req: NextRequest) {
  const searchParams = req.nextUrl.searchParams;
  const queryString = searchParams.toString();
  const url = `${CORE_BACKEND_URL}/api/v1/alerts/silences${queryString ? `?${queryString}` : ''}`;

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'X-Internal-API-Key': INTERNAL_API_KEY,
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

/**
 * POST /api/admin/alerts/silences - 创建静默规则
 */
export async function POST(req: NextRequest) {
  const url = `${CORE_BACKEND_URL}/api/v1/alerts/silences`;

  try {
    const body = await req.json();
    // 注入 created_by
    if (!body.created_by) {
      body.created_by = 'admin_console';
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-API-Key': INTERNAL_API_KEY,
        'X-Operator': 'admin_console',
      },
      body: JSON.stringify(body),
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
