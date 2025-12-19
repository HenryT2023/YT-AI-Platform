import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/iot-devices/stats - 获取设备统计
 */
export async function GET(req: NextRequest) {
  return proxyRequest('/api/v1/iot-devices/stats');
}
