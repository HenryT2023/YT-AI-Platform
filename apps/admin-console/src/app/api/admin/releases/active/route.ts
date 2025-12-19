import { NextRequest, NextResponse } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/releases/active - 获取当前活跃的 Release
 * v0.2.4: tenant/site 由 proxyRequest 从 Header 注入
 */
export async function GET(req: NextRequest) {
  const response = await proxyRequest('/api/v1/releases/active');
  
  // 如果没有活跃的 release，返回 null
  if (response.status === 404) {
    return NextResponse.json(null, { status: 200 });
  }
  
  const data = await response.json();
  return NextResponse.json(data, { status: response.status });
}
