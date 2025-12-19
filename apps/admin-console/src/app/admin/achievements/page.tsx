'use client';

import { useState, useEffect } from 'react';
import { Award, Plus, Edit, Trash2, Gift } from 'lucide-react';

interface Achievement {
  id: string;
  code: string;
  name: string;
  description: string | null;
  icon_url: string | null;
  category: string;
  tier: number;
  points: number;
  rule_type: string;
  rule_config: Record<string, any>;
  is_hidden: boolean;
  is_active: boolean;
  sort_order: number;
  created_at: string;
}

const categoryLabels: Record<string, { label: string; color: string }> = {
  exploration: { label: '探索', color: 'bg-green-100 text-green-700' },
  social: { label: '社交', color: 'bg-blue-100 text-blue-700' },
  learning: { label: '学习', color: 'bg-purple-100 text-purple-700' },
  special: { label: '特殊', color: 'bg-orange-100 text-orange-700' },
};

const tierLabels: Record<number, { label: string; color: string }> = {
  1: { label: '铜', color: 'bg-amber-600 text-white' },
  2: { label: '银', color: 'bg-gray-400 text-white' },
  3: { label: '金', color: 'bg-yellow-500 text-white' },
  4: { label: '钻石', color: 'bg-cyan-400 text-white' },
};

const ruleTypeLabels: Record<string, string> = {
  count: '计数型',
  event: '事件型',
  composite: '组合型',
};

export default function AchievementsPage() {
  const [achievements, setAchievements] = useState<Achievement[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  // 创建成就表单
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [formData, setFormData] = useState({
    code: '',
    name: '',
    description: '',
    category: 'exploration',
    tier: 1,
    points: 10,
    rule_type: 'count',
    rule_metric: 'conversation_count',
    rule_threshold: 10,
    is_hidden: false,
    is_active: true,
  });

  const fetchAchievements = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString(),
      });

      const res = await fetch(`/api/admin/achievements?${params}`);
      if (!res.ok) throw new Error('获取成就列表失败');

      const data = await res.json();
      setAchievements(data.items || []);
      setTotal(data.total || 0);
    } catch (error) {
      console.error('获取成就列表失败:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAchievements();
  }, [page]);

  const handleCreate = async () => {
    if (!formData.code || !formData.name) {
      alert('请填写成就代码和名称');
      return;
    }

    try {
      const ruleConfig: Record<string, any> = {};
      if (formData.rule_type === 'count') {
        ruleConfig.type = 'count';
        ruleConfig.metric = formData.rule_metric;
        ruleConfig.threshold = formData.rule_threshold;
        ruleConfig.operator = 'gte';
      } else if (formData.rule_type === 'event') {
        ruleConfig.type = 'event';
        ruleConfig.event_name = formData.rule_metric;
      }

      const res = await fetch('/api/admin/achievements', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: formData.code,
          name: formData.name,
          description: formData.description || null,
          category: formData.category,
          tier: formData.tier,
          points: formData.points,
          rule_type: formData.rule_type,
          rule_config: ruleConfig,
          is_hidden: formData.is_hidden,
          is_active: formData.is_active,
        }),
      });

      if (res.ok) {
        setShowCreateForm(false);
        setFormData({
          code: '',
          name: '',
          description: '',
          category: 'exploration',
          tier: 1,
          points: 10,
          rule_type: 'count',
          rule_metric: 'conversation_count',
          rule_threshold: 10,
          is_hidden: false,
          is_active: true,
        });
        fetchAchievements();
      } else {
        const error = await res.json();
        alert(error.detail || '创建失败');
      }
    } catch (error) {
      console.error('创建成就失败:', error);
      alert('创建成就失败');
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定要删除成就 "${name}" 吗？`)) return;

    try {
      const res = await fetch(`/api/admin/achievements/${id}`, {
        method: 'DELETE',
      });

      if (res.ok) {
        fetchAchievements();
      } else {
        alert('删除失败');
      }
    } catch (error) {
      console.error('删除成就失败:', error);
      alert('删除成就失败');
    }
  };

  const handleToggleActive = async (achievement: Achievement) => {
    try {
      const res = await fetch(`/api/admin/achievements/${achievement.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !achievement.is_active }),
      });

      if (res.ok) {
        fetchAchievements();
      }
    } catch (error) {
      console.error('更新成就状态失败:', error);
    }
  };

  const getRuleDescription = (achievement: Achievement) => {
    const config = achievement.rule_config;
    if (achievement.rule_type === 'count') {
      return `${config.metric} >= ${config.threshold}`;
    } else if (achievement.rule_type === 'event') {
      return `事件: ${config.event_name}`;
    } else if (achievement.rule_type === 'composite') {
      return `组合规则 (${config.operator})`;
    }
    return '-';
  };

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">成就管理</h1>
          <p className="text-gray-600 mt-1">配置和管理游客成就系统</p>
        </div>
        <button
          onClick={() => setShowCreateForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
        >
          <Plus className="w-5 h-5" />
          创建成就
        </button>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">总成就数</p>
              <p className="text-2xl font-bold text-gray-900">{total}</p>
            </div>
            <Award className="w-8 h-8 text-purple-500" />
          </div>
        </div>

        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">已启用</p>
              <p className="text-2xl font-bold text-green-600">
                {achievements.filter((a) => a.is_active).length}
              </p>
            </div>
            <div className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center">
              <div className="w-3 h-3 bg-green-500 rounded-full" />
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">隐藏成就</p>
              <p className="text-2xl font-bold text-gray-600">
                {achievements.filter((a) => a.is_hidden).length}
              </p>
            </div>
            <div className="w-8 h-8 bg-gray-100 rounded-full flex items-center justify-center">
              <div className="w-3 h-3 bg-gray-400 rounded-full" />
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">总积分值</p>
              <p className="text-2xl font-bold text-orange-600">
                {achievements.reduce((sum, a) => sum + a.points, 0)}
              </p>
            </div>
            <Gift className="w-8 h-8 text-orange-500" />
          </div>
        </div>
      </div>

      {/* 创建成就表单 */}
      {showCreateForm && (
        <div className="bg-white rounded-lg border p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">创建新成就</h2>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                成就代码 *
              </label>
              <input
                type="text"
                value={formData.code}
                onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                placeholder="例如: social_butterfly_1"
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                成就名称 *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="例如: 社交达人 I"
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                描述
              </label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="成就描述"
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                分类
              </label>
              <select
                value={formData.category}
                onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                className="w-full border rounded-lg px-3 py-2"
              >
                <option value="exploration">探索</option>
                <option value="social">社交</option>
                <option value="learning">学习</option>
                <option value="special">特殊</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                等级
              </label>
              <select
                value={formData.tier}
                onChange={(e) => setFormData({ ...formData, tier: parseInt(e.target.value) })}
                className="w-full border rounded-lg px-3 py-2"
              >
                <option value={1}>铜</option>
                <option value={2}>银</option>
                <option value={3}>金</option>
                <option value={4}>钻石</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                积分值
              </label>
              <input
                type="number"
                value={formData.points}
                onChange={(e) => setFormData({ ...formData, points: parseInt(e.target.value) })}
                min="0"
                className="w-full border rounded-lg px-3 py-2"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                规则类型
              </label>
              <select
                value={formData.rule_type}
                onChange={(e) => setFormData({ ...formData, rule_type: e.target.value })}
                className="w-full border rounded-lg px-3 py-2"
              >
                <option value="count">计数型</option>
                <option value="event">事件型</option>
              </select>
            </div>
            {formData.rule_type === 'count' && (
              <>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    指标
                  </label>
                  <select
                    value={formData.rule_metric}
                    onChange={(e) => setFormData({ ...formData, rule_metric: e.target.value })}
                    className="w-full border rounded-lg px-3 py-2"
                  >
                    <option value="conversation_count">对话次数</option>
                    <option value="visit_count">访问次数</option>
                    <option value="check_in_count">打卡次数</option>
                    <option value="quest_completed_count">任务完成数</option>
                    <option value="total_duration_minutes">总停留时长(分钟)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    阈值
                  </label>
                  <input
                    type="number"
                    value={formData.rule_threshold}
                    onChange={(e) =>
                      setFormData({ ...formData, rule_threshold: parseInt(e.target.value) })
                    }
                    min="1"
                    className="w-full border rounded-lg px-3 py-2"
                  />
                </div>
              </>
            )}
            {formData.rule_type === 'event' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  事件名
                </label>
                <input
                  type="text"
                  value={formData.rule_metric}
                  onChange={(e) => setFormData({ ...formData, rule_metric: e.target.value })}
                  placeholder="例如: first_conversation"
                  className="w-full border rounded-lg px-3 py-2"
                />
              </div>
            )}
            <div className="col-span-2 flex items-center gap-6">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="rounded"
                />
                <span className="text-sm text-gray-700">启用</span>
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={formData.is_hidden}
                  onChange={(e) => setFormData({ ...formData, is_hidden: e.target.checked })}
                  className="rounded"
                />
                <span className="text-sm text-gray-700">隐藏成就</span>
              </label>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              onClick={handleCreate}
              className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
            >
              创建
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

      {/* 成就列表 */}
      <div className="bg-white rounded-lg border">
        {loading ? (
          <div className="p-8 text-center text-gray-500">加载中...</div>
        ) : achievements.length === 0 ? (
          <div className="p-8 text-center text-gray-500">暂无成就，点击上方按钮创建</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">成就</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">分类</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">等级</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">积分</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">规则</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">状态</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {achievements.map((achievement) => (
                  <tr key={achievement.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div>
                        <p className="font-medium text-gray-900">{achievement.name}</p>
                        <p className="text-xs text-gray-500 font-mono">{achievement.code}</p>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-medium rounded ${
                          categoryLabels[achievement.category]?.color || 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {categoryLabels[achievement.category]?.label || achievement.category}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-medium rounded ${
                          tierLabels[achievement.tier]?.color || 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {tierLabels[achievement.tier]?.label || achievement.tier}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">{achievement.points}</td>
                    <td className="px-4 py-3">
                      <div className="text-sm">
                        <span className="text-gray-500">
                          {ruleTypeLabels[achievement.rule_type] || achievement.rule_type}
                        </span>
                        <p className="text-xs text-gray-400 font-mono">
                          {getRuleDescription(achievement)}
                        </p>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => handleToggleActive(achievement)}
                        className={`inline-flex px-2 py-1 text-xs font-medium rounded ${
                          achievement.is_active
                            ? 'bg-green-100 text-green-700'
                            : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {achievement.is_active ? '已启用' : '已禁用'}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleDelete(achievement.id, achievement.name)}
                          className="p-1 hover:bg-red-50 rounded text-red-600"
                          title="删除"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 分页 */}
        {total > pageSize && (
          <div className="px-4 py-3 border-t flex items-center justify-between">
            <div className="text-sm text-gray-600">
              共 {total} 条，第 {page} / {Math.ceil(total / pageSize)} 页
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(1, page - 1))}
                disabled={page === 1}
                className="px-3 py-1 border rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                上一页
              </button>
              <button
                onClick={() => setPage(Math.min(Math.ceil(total / pageSize), page + 1))}
                disabled={page >= Math.ceil(total / pageSize)}
                className="px-3 py-1 border rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
