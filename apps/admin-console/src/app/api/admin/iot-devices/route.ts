import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/iot-devices - 获取设备列表
 * POST /api/admin/iot-devices - 注册设备
 */
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const params = searchParams.toString();
  return proxyRequest(`/api/v1/iot-devices${params ? `?${params}` : ''}`);
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  return proxyRequest('/api/v1/iot-devices', {
    method: 'POST',
    body,
  });
}
