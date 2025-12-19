import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/alerts/events - 获取告警事件列表
 * v0.2.4: tenant/site 由 proxyRequest 从 Header 注入
 */
export async function GET(req: NextRequest) {
  return proxyRequest('/api/v1/alerts/events', { searchParams: req.nextUrl.searchParams });
}
