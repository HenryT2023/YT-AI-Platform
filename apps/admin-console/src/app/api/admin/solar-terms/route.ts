import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/solar-terms - 获取节气列表
 */
export async function GET(req: NextRequest) {
  return proxyRequest('/api/v1/solar-terms');
}
