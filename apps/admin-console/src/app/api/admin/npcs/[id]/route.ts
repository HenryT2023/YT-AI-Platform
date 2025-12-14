import { NextRequest, NextResponse } from 'next/server';

const CORE_BACKEND_URL = process.env.CORE_BACKEND_URL || 'http://localhost:8000';
const INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || '';

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const url = `${CORE_BACKEND_URL}/api/v1/npcs/${params.id}`;

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

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const url = `${CORE_BACKEND_URL}/api/v1/npcs/${params.id}`;

  try {
    const body = await req.json();
    const response = await fetch(url, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-Internal-API-Key': INTERNAL_API_KEY,
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

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const url = `${CORE_BACKEND_URL}/api/v1/npcs/${params.id}`;

  try {
    const response = await fetch(url, {
      method: 'DELETE',
      headers: {
        'X-Internal-API-Key': INTERNAL_API_KEY,
      },
    });

    if (response.status === 204) {
      return new NextResponse(null, { status: 204 });
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
