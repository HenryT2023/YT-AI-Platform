import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/solar-terms/current - 获取当前节气
 */
export async function GET(req: NextRequest) {
  return proxyRequest('/api/v1/solar-terms/current');
}
