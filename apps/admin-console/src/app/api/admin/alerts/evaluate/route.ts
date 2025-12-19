import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * POST /api/admin/alerts/evaluate - 手动触发告警评估
 * v0.2.4: tenant/site 由 proxyRequest 从 Header 注入
 */
export async function POST(req: NextRequest) {
  return proxyRequest('/api/v1/alerts/evaluate-persist', { method: 'POST' });
}
