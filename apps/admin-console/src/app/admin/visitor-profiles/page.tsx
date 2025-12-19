'use client';

import { useState, useEffect } from 'react';
import { Users, TrendingUp, Clock, MessageSquare, Award, MapPin, Tag } from 'lucide-react';
import Link from 'next/link';

interface VisitorProfile {
  id: string;
  user_id: string;
  visit_count: number;
  total_duration_minutes: number;
  conversation_count: number;
  quest_completed_count: number;
  achievement_count: number;
  check_in_count: number;
  activity_level: string;
  engagement_score: number;
  learning_style: string | null;
  first_visit_at: string;
  last_visit_at: string;
  last_active_at: string;
}

const activityLevelLabels: Record<string, { label: string; color: string }> = {
  new: { label: '新手', color: 'bg-gray-100 text-gray-700' },
  casual: { label: '休闲', color: 'bg-blue-100 text-blue-700' },
  active: { label: '活跃', color: 'bg-green-100 text-green-700' },
  power: { label: '核心', color: 'bg-purple-100 text-purple-700' },
};

export default function VisitorProfilesPage() {
  const [profiles, setProfiles] = useState<VisitorProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  
  // 过滤条件
  const [activityFilter, setActivityFilter] = useState<string>('');
  const [minEngagement, setMinEngagement] = useState<string>('');

  const fetchProfiles = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString(),
      });
      
      if (activityFilter) params.append('activity_level', activityFilter);
      if (minEngagement) params.append('min_engagement', minEngagement);

      const res = await fetch(`/api/admin/visitor-profiles?${params}`);
      if (!res.ok) throw new Error('获取画像列表失败');
      
      const data = await res.json();
      setProfiles(data.items || []);
      setTotal(data.total || 0);
    } catch (error) {
      console.error('获取画像列表失败:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProfiles();
  }, [page, activityFilter, minEngagement]);

  const formatDuration = (minutes: number) => {
    if (minutes < 60) return `${minutes}分钟`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}小时${mins > 0 ? mins + '分钟' : ''}`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  };

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">游客画像</h1>
        <p className="text-gray-600 mt-1">查看和管理游客行为画像与标签</p>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">总画像数</p>
              <p className="text-2xl font-bold text-gray-900">{total}</p>
            </div>
            <Users className="w-8 h-8 text-blue-500" />
          </div>
        </div>
        
        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">活跃用户</p>
              <p className="text-2xl font-bold text-green-600">
                {profiles.filter(p => p.activity_level === 'active' || p.activity_level === 'power').length}
              </p>
            </div>
            <TrendingUp className="w-8 h-8 text-green-500" />
          </div>
        </div>

        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">平均参与度</p>
              <p className="text-2xl font-bold text-purple-600">
                {profiles.length > 0
                  ? (profiles.reduce((sum, p) => sum + p.engagement_score, 0) / profiles.length).toFixed(1)
                  : '0'}
              </p>
            </div>
            <Award className="w-8 h-8 text-purple-500" />
          </div>
        </div>

        <div className="bg-white rounded-lg border p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-600">总对话数</p>
              <p className="text-2xl font-bold text-orange-600">
                {profiles.reduce((sum, p) => sum + p.conversation_count, 0)}
              </p>
            </div>
            <MessageSquare className="w-8 h-8 text-orange-500" />
          </div>
        </div>
      </div>

      {/* 过滤器 */}
      <div className="bg-white rounded-lg border p-4 mb-6">
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              活跃度
            </label>
            <select
              value={activityFilter}
              onChange={(e) => {
                setActivityFilter(e.target.value);
                setPage(1);
              }}
              className="w-full border rounded-lg px-3 py-2"
            >
              <option value="">全部</option>
              <option value="new">新手</option>
              <option value="casual">休闲</option>
              <option value="active">活跃</option>
              <option value="power">核心</option>
            </select>
          </div>

          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              最小参与度
            </label>
            <input
              type="number"
              value={minEngagement}
              onChange={(e) => {
                setMinEngagement(e.target.value);
                setPage(1);
              }}
              placeholder="0-100"
              min="0"
              max="100"
              className="w-full border rounded-lg px-3 py-2"
            />
          </div>

          <div className="flex items-end">
            <button
              onClick={() => {
                setActivityFilter('');
                setMinEngagement('');
                setPage(1);
              }}
              className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg"
            >
              重置
            </button>
          </div>
        </div>
      </div>

      {/* 画像列表 */}
      <div className="bg-white rounded-lg border">
        {loading ? (
          <div className="p-8 text-center text-gray-500">加载中...</div>
        ) : profiles.length === 0 ? (
          <div className="p-8 text-center text-gray-500">暂无画像数据</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">用户 ID</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">活跃度</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">参与度</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">访问次数</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">停留时长</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">对话</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">任务</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">打卡</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">最后活跃</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-700">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {profiles.map((profile) => (
                  <tr key={profile.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm">
                      <div className="font-mono text-xs text-gray-600">
                        {profile.user_id.slice(0, 8)}...
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-medium rounded ${
                          activityLevelLabels[profile.activity_level]?.color || 'bg-gray-100 text-gray-700'
                        }`}
                      >
                        {activityLevelLabels[profile.activity_level]?.label || profile.activity_level}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-blue-500 h-2 rounded-full"
                            style={{ width: `${profile.engagement_score}%` }}
                          />
                        </div>
                        <span className="text-sm text-gray-600">{profile.engagement_score.toFixed(0)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">{profile.visit_count}</td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {formatDuration(profile.total_duration_minutes)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">{profile.conversation_count}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{profile.quest_completed_count}</td>
                    <td className="px-4 py-3 text-sm text-gray-900">{profile.check_in_count}</td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {formatDate(profile.last_active_at)}
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/admin/visitor-profiles/${profile.id}`}
                        className="text-primary-600 hover:text-primary-700 text-sm font-medium"
                      >
                        查看详情
                      </Link>
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
