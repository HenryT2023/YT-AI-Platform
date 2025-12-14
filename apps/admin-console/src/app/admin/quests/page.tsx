'use client';

import { useState, useEffect } from 'react';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import {
  Trophy,
  Plus,
  Edit2,
  Trash2,
  RefreshCw,
  Loader2,
  ChevronDown,
  ChevronUp,
  Target,
  Gift,
} from 'lucide-react';

interface Quest {
  id: string;
  site_id: string;
  name: string;
  display_name?: string;
  description?: string;
  quest_type?: string;
  difficulty?: string;
  estimated_duration_minutes?: number;
  rewards?: Record<string, any>;
  requirements?: Record<string, any>;
  steps?: any[];
  sort_order: number;
  status: string;
}

const QUEST_TYPE_LABELS: Record<string, string> = {
  exploration: '探索',
  learning: '学习',
  collection: '收集',
  interaction: '互动',
  challenge: '挑战',
};

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: 'bg-green-100 text-green-700',
  medium: 'bg-yellow-100 text-yellow-700',
  hard: 'bg-orange-100 text-orange-700',
  expert: 'bg-red-100 text-red-700',
};

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  inactive: 'bg-gray-100 text-gray-700',
  draft: 'bg-yellow-100 text-yellow-700',
};

export default function QuestsPage() {
  const [quests, setQuests] = useState<Quest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>('');

  const fetchQuests = async () => {
    setLoading(true);
    setError(null);
    try {
      let url = '/api/admin/quests';
      if (typeFilter) url += `?quest_type=${typeFilter}`;
      const res = await fetch(url);
      const data = await res.json();
      setQuests(Array.isArray(data) ? data : []);
    } catch (err: any) {
      setError(err.message || '获取任务列表失败');
      setQuests([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQuests();
  }, [typeFilter]);

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定要删除任务「${name}」吗？此操作不可恢复。`)) return;
    try {
      await fetch(`/api/admin/quests/${id}`, { method: 'DELETE' });
      await fetchQuests();
    } catch (err: any) {
      alert(err.message || '删除失败');
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">任务管理</h1>
            <p className="mt-1 text-sm text-gray-500">配置研学任务与奖励机制</p>
          </div>
          <button
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
            onClick={() => alert('创建功能开发中')}
          >
            <Plus className="w-4 h-4" />
            新建任务
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
            <option value="exploration">探索</option>
            <option value="learning">学习</option>
            <option value="collection">收集</option>
            <option value="interaction">互动</option>
            <option value="challenge">挑战</option>
          </select>
          <button
            onClick={fetchQuests}
            className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-900"
          >
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
          <span className="text-sm text-gray-500">
            共 {quests.length} 个任务
          </span>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
            {error}
          </div>
        )}

        {/* 任务列表 */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : quests.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            暂无任务数据
          </div>
        ) : (
          <div className="space-y-3">
            {quests.map((quest) => (
              <div
                key={quest.id}
                className="bg-white border rounded-lg shadow-sm overflow-hidden"
              >
                <div className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
                        <Trophy className="w-5 h-5 text-amber-600" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900">
                            {quest.display_name || quest.name}
                          </span>
                          {quest.quest_type && (
                            <span className="px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-700">
                              {QUEST_TYPE_LABELS[quest.quest_type] || quest.quest_type}
                            </span>
                          )}
                          {quest.difficulty && (
                            <span className={`px-2 py-0.5 rounded text-xs ${DIFFICULTY_COLORS[quest.difficulty] || 'bg-gray-100 text-gray-700'}`}>
                              {quest.difficulty}
                            </span>
                          )}
                          <span className={`px-2 py-0.5 rounded text-xs ${STATUS_COLORS[quest.status] || 'bg-gray-100 text-gray-700'}`}>
                            {quest.status}
                          </span>
                        </div>
                        <div className="text-sm text-gray-500">
                          ID: {quest.id.slice(0, 8)}...
                          {quest.estimated_duration_minutes && (
                            <span className="ml-2">⏱ {quest.estimated_duration_minutes} 分钟</span>
                          )}
                          {quest.steps && (
                            <span className="ml-2">📋 {quest.steps.length} 步骤</span>
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
                        onClick={() => handleDelete(quest.id, quest.display_name || quest.name)}
                        className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setExpandedId(expandedId === quest.id ? null : quest.id)}
                        className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
                      >
                        {expandedId === quest.id ? (
                          <ChevronUp className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {/* 展开详情 */}
                {expandedId === quest.id && (
                  <div className="border-t bg-gray-50 p-4">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        {quest.description && (
                          <div className="mb-2">
                            <span className="font-medium text-gray-700">描述:</span>
                            <p className="mt-1 text-gray-600">{quest.description}</p>
                          </div>
                        )}
                        {quest.requirements && (
                          <div>
                            <span className="font-medium text-gray-700 flex items-center gap-1">
                              <Target className="w-4 h-4" /> 前置条件:
                            </span>
                            <pre className="mt-1 p-2 bg-white rounded border text-xs overflow-auto max-h-32">
                              {JSON.stringify(quest.requirements, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                      <div className="space-y-2">
                        {quest.rewards && (
                          <div>
                            <span className="font-medium text-gray-700 flex items-center gap-1">
                              <Gift className="w-4 h-4" /> 奖励:
                            </span>
                            <pre className="mt-1 p-2 bg-white rounded border text-xs overflow-auto max-h-32">
                              {JSON.stringify(quest.rewards, null, 2)}
                            </pre>
                          </div>
                        )}
                        {quest.steps && quest.steps.length > 0 && (
                          <div>
                            <span className="font-medium text-gray-700">步骤预览:</span>
                            <ol className="mt-1 list-decimal list-inside text-gray-600 text-xs">
                              {quest.steps.slice(0, 5).map((step: any, i: number) => (
                                <li key={i} className="truncate">
                                  {step.name || step.description || `步骤 ${i + 1}`}
                                </li>
                              ))}
                              {quest.steps.length > 5 && (
                                <li className="text-gray-400">...还有 {quest.steps.length - 5} 个步骤</li>
                              )}
                            </ol>
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
