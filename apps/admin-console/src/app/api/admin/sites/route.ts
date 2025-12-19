import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/sites - 获取站点列表
 * v0.2.4: 用于站点切换器
 */
export async function GET(req: NextRequest) {
  return proxyRequest('/api/v1/sites', { searchParams: req.nextUrl.searchParams });
}
