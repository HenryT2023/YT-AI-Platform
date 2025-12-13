import { NextRequest, NextResponse } from 'next/server';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || '';

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const url = `${CORE_BACKEND_URL}/api/v1/feedback/${params.id}/triage`;
  
  try {
    const body = await req.json();
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-API-Key': INTERNAL_API_KEY,
        'X-Operator': 'admin_console',
        'X-Tenant-ID': req.headers.get('X-Tenant-ID') || 'yantian',
        'X-Site-ID': req.headers.get('X-Site-ID') || 'yantian-main',
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
