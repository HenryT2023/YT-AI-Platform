'use client';

import { useState, useEffect } from 'react';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { scenesApi } from '@/lib/api';
import {
  MapPin,
  Plus,
  Edit2,
  Trash2,
  RefreshCw,
  Loader2,
  ChevronDown,
  ChevronUp,
  Navigation,
} from 'lucide-react';

interface Scene {
  id: string;
  site_id: string;
  name: string;
  display_name?: string;
  description?: string;
  scene_type?: string;
  location_lat?: number;
  location_lng?: number;
  boundary?: Record<string, any>;
  config: Record<string, any>;
  parent_scene_id?: string;
  sort_order: number;
  status: string;
}

const SCENE_TYPE_LABELS: Record<string, string> = {
  village: '村落',
  building: '建筑',
  landmark: '地标',
  area: '区域',
  poi: 'POI',
};

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  inactive: 'bg-gray-100 text-gray-700',
  draft: 'bg-yellow-100 text-yellow-700',
};

export default function ScenesPage() {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchScenes = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await scenesApi.list();
      const data = res.data;
      setScenes(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err.message || '获取场景列表失败');
      setScenes([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScenes();
  }, []);

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定要删除场景「${name}」吗？此操作不可恢复。`)) return;
    try {
      await scenesApi.delete(id);
      await fetchScenes();
    } catch (err: any) {
      alert(err.message || '删除失败');
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">场景管理</h1>
            <p className="mt-1 text-sm text-gray-500">管理景区场景与 POI 点位</p>
          </div>
          <button
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            onClick={() => alert('创建功能开发中')}
          >
            <Plus className="w-4 h-4" />
            新建场景
          </button>
        </div>

        {/* 工具栏 */}
        <div className="flex items-center gap-4">
          <button
            onClick={fetchScenes}
            className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-900"
          >
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
          <span className="text-sm text-gray-500">
            共 {scenes.length} 个场景
          </span>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
            {error}
          </div>
        )}

        {/* 场景列表 */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : scenes.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            暂无场景数据
          </div>
        ) : (
          <div className="space-y-3">
            {scenes.map((scene) => (
              <div
                key={scene.id}
                className="bg-white border rounded-lg shadow-sm overflow-hidden"
              >
                <div className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                        <MapPin className="w-5 h-5 text-blue-600" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900">
                            {scene.display_name || scene.name}
                          </span>
                          {scene.scene_type && (
                            <span className="px-2 py-0.5 rounded text-xs bg-purple-100 text-purple-700">
                              {SCENE_TYPE_LABELS[scene.scene_type] || scene.scene_type}
                            </span>
                          )}
                          <span className={`px-2 py-0.5 rounded text-xs ${STATUS_COLORS[scene.status] || 'bg-gray-100 text-gray-700'}`}>
                            {scene.status}
                          </span>
                        </div>
                        <div className="text-sm text-gray-500">
                          ID: {scene.id.slice(0, 8)}... | 排序: {scene.sort_order}
                          {scene.location_lat && scene.location_lng && (
                            <span className="ml-2">
                              <Navigation className="w-3 h-3 inline" /> {scene.location_lat.toFixed(4)}, {scene.location_lng.toFixed(4)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => alert('编辑功能开发中')}
                        className="p-2 text-gray-400 hover:text-blue-600 transition-colors"
                        title="编辑"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(scene.id, scene.display_name || scene.name)}
                        className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setExpandedId(expandedId === scene.id ? null : scene.id)}
                        className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
                      >
                        {expandedId === scene.id ? (
                          <ChevronUp className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {/* 展开详情 */}
                {expandedId === scene.id && (
                  <div className="border-t bg-gray-50 p-4">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        {scene.description && (
                          <div className="mb-2">
                            <span className="font-medium text-gray-700">描述:</span>
                            <p className="mt-1 text-gray-600">{scene.description}</p>
                          </div>
                        )}
                        <div>
                          <span className="font-medium text-gray-700">配置:</span>
                          <pre className="mt-1 p-2 bg-white rounded border text-xs overflow-auto max-h-40">
                            {JSON.stringify(scene.config, null, 2)}
                          </pre>
                        </div>
                      </div>
                      <div className="space-y-2">
                        {scene.parent_scene_id && (
                          <div>
                            <span className="font-medium text-gray-700">父场景 ID:</span>
                            <span className="ml-2 text-gray-600 font-mono text-xs">{scene.parent_scene_id}</span>
                          </div>
                        )}
                        {scene.boundary && (
                          <div>
                            <span className="font-medium text-gray-700">边界数据:</span>
                            <pre className="mt-1 p-2 bg-white rounded border text-xs overflow-auto max-h-20">
                              {JSON.stringify(scene.boundary, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
