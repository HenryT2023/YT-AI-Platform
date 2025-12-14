'use client';

import { useState, useEffect } from 'react';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { npcsApi } from '@/lib/api';
import {
  MessageSquare,
  Plus,
  Edit2,
  Trash2,
  RefreshCw,
  Loader2,
  User,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

interface NPC {
  id: string;
  site_id: string;
  name: string;
  display_name?: string;
  npc_type?: string;
  persona: Record<string, any>;
  avatar_asset_id?: string;
  voice_id?: string;
  scene_ids?: string[];
  greeting_templates?: string[];
  fallback_responses?: string[];
  status: string;
}

const NPC_TYPE_LABELS: Record<string, string> = {
  ancestor: '先祖',
  craftsman: '匠人',
  farmer: '农人',
  teacher: '先生',
};

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  inactive: 'bg-gray-100 text-gray-700',
  draft: 'bg-yellow-100 text-yellow-700',
};

export default function NpcsPage() {
  const [npcs, setNpcs] = useState<NPC[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>('');

  const fetchNpcs = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: any = {};
      if (typeFilter) params.npc_type = typeFilter;
      const res = await npcsApi.list(params);
      const data = res.data;
      setNpcs(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err.message || '获取 NPC 列表失败');
      setNpcs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNpcs();
  }, [typeFilter]);

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定要删除 NPC「${name}」吗？此操作不可恢复。`)) return;
    try {
      await npcsApi.delete(id);
      await fetchNpcs();
    } catch (err: any) {
      alert(err.message || '删除失败');
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">NPC 管理</h1>
            <p className="mt-1 text-sm text-gray-500">管理 AI 导览角色的人设与配置</p>
          </div>
          <button
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            onClick={() => alert('创建功能开发中')}
          >
            <Plus className="w-4 h-4" />
            新建 NPC
          </button>
        </div>

        {/* 筛选栏 */}
        <div className="flex items-center gap-4">
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="border rounded-md px-3 py-2 text-sm"
          >
            <option value="">全部类型</option>
            <option value="ancestor">先祖</option>
            <option value="craftsman">匠人</option>
            <option value="farmer">农人</option>
            <option value="teacher">先生</option>
          </select>
          <button
            onClick={fetchNpcs}
            className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-900"
          >
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
          <span className="text-sm text-gray-500">
            共 {npcs.length} 个 NPC
          </span>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
            {error}
          </div>
        )}

        {/* NPC 列表 */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : npcs.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            暂无 NPC 数据
          </div>
        ) : (
          <div className="space-y-3">
            {npcs.map((npc) => (
              <div
                key={npc.id}
                className="bg-white border rounded-lg shadow-sm overflow-hidden"
              >
                <div className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center">
                        <User className="w-5 h-5 text-primary-600" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900">
                            {npc.display_name || npc.name}
                          </span>
                          {npc.npc_type && (
                            <span className="px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-700">
                              {NPC_TYPE_LABELS[npc.npc_type] || npc.npc_type}
                            </span>
                          )}
                          <span className={`px-2 py-0.5 rounded text-xs ${STATUS_COLORS[npc.status] || 'bg-gray-100 text-gray-700'}`}>
                            {npc.status}
                          </span>
                        </div>
                        <div className="text-sm text-gray-500">
                          ID: {npc.id.slice(0, 8)}... | 站点: {npc.site_id}
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
                        onClick={() => handleDelete(npc.id, npc.display_name || npc.name)}
                        className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setExpandedId(expandedId === npc.id ? null : npc.id)}
                        className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
                      >
                        {expandedId === npc.id ? (
                          <ChevronUp className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {/* 展开详情 */}
                {expandedId === npc.id && (
                  <div className="border-t bg-gray-50 p-4">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="font-medium text-gray-700">人设配置:</span>
                        <pre className="mt-1 p-2 bg-white rounded border text-xs overflow-auto max-h-40">
                          {JSON.stringify(npc.persona, null, 2)}
                        </pre>
                      </div>
                      <div className="space-y-2">
                        {npc.greeting_templates && npc.greeting_templates.length > 0 && (
                          <div>
                            <span className="font-medium text-gray-700">问候语模板:</span>
                            <ul className="mt-1 list-disc list-inside text-gray-600">
                              {npc.greeting_templates.slice(0, 3).map((t, i) => (
                                <li key={i} className="truncate">{t}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {npc.voice_id && (
                          <div>
                            <span className="font-medium text-gray-700">语音 ID:</span>
                            <span className="ml-2 text-gray-600">{npc.voice_id}</span>
                          </div>
                        )}
                        {npc.scene_ids && npc.scene_ids.length > 0 && (
                          <div>
                            <span className="font-medium text-gray-700">关联场景:</span>
                            <span className="ml-2 text-gray-600">{npc.scene_ids.length} 个</span>
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
