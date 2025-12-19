import { NextRequest } from 'next/server';
import { proxyRequest } from '@/lib/auth-utils';

/**
 * GET /api/admin/iot-devices/[id] - 获取设备详情
 * PATCH /api/admin/iot-devices/[id] - 更新设备
 * DELETE /api/admin/iot-devices/[id] - 删除设备
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/iot-devices/${params.id}`);
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const body = await req.json();
  return proxyRequest(`/api/v1/iot-devices/${params.id}`, {
    method: 'PATCH',
    body,
  });
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  return proxyRequest(`/api/v1/iot-devices/${params.id}`, {
    method: 'DELETE',
  });
}
