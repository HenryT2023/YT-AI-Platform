'use client';

import { useState, useEffect } from 'react';
import { Wifi, WifiOff, Plus, Trash2, RefreshCw, AlertCircle } from 'lucide-react';

interface IoTDevice {
  id: string;
  device_code: string;
  name: string;
  device_type: string;
  location: string | null;
  status: string;
  last_heartbeat: string | null;
  is_active: boolean;
  created_at: string;
}

const deviceTypeLabels: Record<string, { label: string; icon: string }> = {
  light: { label: '灯光', icon: '💡' },
  speaker: { label: '音响', icon: '🔊' },
  sensor: { label: '传感器', icon: '📡' },
  camera: { label: '摄像头', icon: '📷' },
  display: { label: '显示屏', icon: '🖥️' },
  other: { label: '其他', icon: '📦' },
};

const statusColors: Record<string, string> = {
  online: 'bg-green-100 text-green-700',
  offline: 'bg-gray-100 text-gray-500',
  error: 'bg-red-100 text-red-700',
};

export default function IoTDevicesPage() {
  const [devices, setDevices] = useState<IoTDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState({ online: 0, offline: 0, error: 0, by_type: {} as Record<string, number> });

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [formData, setFormData] = useState({
    device_code: '',
    name: '',
    device_type: 'other',
    location: '',
  });

  const fetchDevices = async () => {
    setLoading(true);
    try {
      const [devicesRes, statsRes] = await Promise.all([
        fetch('/api/admin/iot-devices'),
        fetch('/api/admin/iot-devices/stats'),
      ]);

      if (devicesRes.ok) {
        const data = await devicesRes.json();
        setDevices(data.items || []);
        setTotal(data.total || 0);
      }

      if (statsRes.ok) {
        const data = await statsRes.json();
        setStats(data);
      }
    } catch (error) {
      console.error('获取设备列表失败:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDevices();
  }, []);

  const handleCreate = async () => {
    if (!formData.device_code || !formData.name) {
      alert('请填写设备编码和名称');
      return;
    }

    try {
      const res = await fetch('/api/admin/iot-devices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_code: formData.device_code,
          name: formData.name,
          device_type: formData.device_type,
          location: formData.location || null,
        }),
      });

      if (res.ok) {
        setShowCreateForm(false);
        setFormData({ device_code: '', name: '', device_type: 'other', location: '' });
        fetchDevices();
      } else {
        const error = await res.json();
        alert(error.detail || '创建失败');
      }
    } catch (error) {
      console.error('创建设备失败:', error);
      alert('创建设备失败');
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定要删除设备 "${name}" 吗？`)) return;

    try {
      const res = await fetch(`/api/admin/iot-devices/${id}`, { method: 'DELETE' });
      if (res.ok) {
        fetchDevices();
      } else {
        alert('删除失败');
      }
    } catch (error) {
      console.error('删除设备失败:', error);
    }
  };

  const formatTime = (time: string | null) => {
    if (!time) return '-';
    const date = new Date(time);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes}分钟前`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}小时前`;
    return date.toLocaleDateString();
  };

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">IoT 设备管理</h1>
          <p className="text-gray-600 mt-1">管理现场 IoT 设备</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchDevices}
            className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-gray-50"
          >
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
          <button
            onClick={() => setShowCreateForm(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            <Plus className="w-5 h-5" />
            注册设备
          </button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">总设备数</p>
              <p className="text-2xl font-bold text-gray-900">{total}</p>
            </div>
            <Wifi className="w-8 h-8 text-blue-500" />
          </div>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">在线</p>
              <p className="text-2xl font-bold text-green-600">{stats.online}</p>
            </div>
            <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
              <div className="w-3 h-3 bg-green-500 rounded-full animate-pulse" />
            </div>
          </div>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">离线</p>
              <p className="text-2xl font-bold text-gray-500">{stats.offline}</p>
            </div>
            <WifiOff className="w-8 h-8 text-gray-400" />
          </div>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">故障</p>
              <p className="text-2xl font-bold text-red-600">{stats.error}</p>
            </div>
            <AlertCircle className="w-8 h-8 text-red-500" />
          </div>
        </div>
      </div>

      {/* 创建设备表单 */}
      {showCreateForm && (
        <div className="bg-white rounded-lg border p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">注册新设备</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                设备编码 *
              </label>
              <input
                type="text"
                value={formData.device_code}
                onChange={(e) => setFormData({ ...formData, device_code: e.target.value })}
                placeholder="例如: LIGHT-001"
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                设备名称 *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="例如: 祠堂入口灯"
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                设备类型
              </label>
              <select
                value={formData.device_type}
                onChange={(e) => setFormData({ ...formData, device_type: e.target.value })}
                className="w-full border rounded-lg px-3 py-2"
              >
                {Object.entries(deviceTypeLabels).map(([key, { label, icon }]) => (
                  <option key={key} value={key}>
                    {icon} {label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                位置描述
              </label>
              <input
                type="text"
                value={formData.location}
                onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                placeholder="例如: 敦本堂正门"
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              onClick={handleCreate}
              className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
            >
              注册
            </button>
            <button
              onClick={() => setShowCreateForm(false)}
              className="px-4 py-2 border rounded-lg hover:bg-gray-50"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {/* 设备列表 */}
      <div className="bg-white rounded-lg border">
        {loading ? (
          <div className="p-8 text-center text-gray-500">加载中...</div>
        ) : devices.length === 0 ? (
          <div className="p-8 text-center text-gray-500">暂无设备，点击上方按钮注册</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">设备</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">类型</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">位置</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">状态</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">最后心跳</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {devices.map((device) => (
                  <tr key={device.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div>
                        <p className="font-medium text-gray-900">{device.name}</p>
                        <p className="text-xs text-gray-500 font-mono">{device.device_code}</p>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm">
                        {deviceTypeLabels[device.device_type]?.icon}{' '}
                        {deviceTypeLabels[device.device_type]?.label || device.device_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {device.location || '-'}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-medium rounded ${
                          statusColors[device.status] || 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {device.status === 'online' ? '在线' : device.status === 'error' ? '故障' : '离线'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {formatTime(device.last_heartbeat)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleDelete(device.id, device.name)}
                        className="p-1 hover:bg-red-50 rounded text-red-600"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
