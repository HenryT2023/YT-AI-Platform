'use client';

import { useState, useEffect } from 'react';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import {
  Users,
  RefreshCw,
  Loader2,
  ChevronDown,
  ChevronUp,
  User,
  Calendar,
  Trophy,
} from 'lucide-react';
import { format } from 'date-fns';

interface Visitor {
  id: string;
  nickname?: string;
  avatar_url?: string;
  phone?: string;
  created_at: string;
  last_active_at?: string;
  visit_count?: number;
  total_chat_count?: number;
  completed_quest_count?: number;
}

export default function VisitorsPage() {
  const [visitors, setVisitors] = useState<Visitor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const fetchVisitors = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/visitors?skip=${page * pageSize}&limit=${pageSize}`);
      const data = await res.json();
      if (Array.isArray(data)) {
        setVisitors(data);
      } else if (data && Array.isArray(data.items)) {
        setVisitors(data.items);
      } else {
        setVisitors([]);
      }
    } catch (err: any) {
      setError(err.message || '获取访客列表失败');
      setVisitors([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchVisitors();
  }, [page]);

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '-';
    try {
      return format(new Date(dateStr), 'yyyy-MM-dd HH:mm');
    } catch {
      return dateStr;
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">访客数据</h1>
            <p className="mt-1 text-sm text-gray-500">查看访客画像与行为分析</p>
          </div>
        </div>

        {/* 工具栏 */}
        <div className="flex items-center gap-4">
          <button
            onClick={fetchVisitors}
            className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-900"
          >
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
          <span className="text-sm text-gray-500">
            当前页 {visitors.length} 条记录
          </span>
          <div className="flex items-center gap-2 ml-auto">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-3 py-1 text-sm border rounded disabled:opacity-50"
            >
              上一页
            </button>
            <span className="text-sm text-gray-600">第 {page + 1} 页</span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={visitors.length < pageSize}
              className="px-3 py-1 text-sm border rounded disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
            {error}
          </div>
        )}

        {/* 访客列表 */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
          </div>
        ) : visitors.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            暂无访客数据
          </div>
        ) : (
          <div className="bg-white border rounded-lg shadow-sm overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">访客</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">注册时间</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">最后活跃</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">访问次数</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">对话次数</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">完成任务</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {visitors.map((visitor) => (
                  <tr key={visitor.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center overflow-hidden">
                          {visitor.avatar_url ? (
                            <img src={visitor.avatar_url} alt="" className="w-full h-full object-cover" />
                          ) : (
                            <User className="w-4 h-4 text-gray-400" />
                          )}
                        </div>
                        <div>
                          <div className="text-sm font-medium text-gray-900">
                            {visitor.nickname || '匿名访客'}
                          </div>
                          <div className="text-xs text-gray-500 font-mono">
                            {visitor.id.slice(0, 8)}...
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {formatDate(visitor.created_at)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {formatDate(visitor.last_active_at)}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {visitor.visit_count ?? '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {visitor.total_chat_count ?? '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {visitor.completed_quest_count ?? '-'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => setExpandedId(expandedId === visitor.id ? null : visitor.id)}
                        className="text-sm text-blue-600 hover:text-blue-800"
                      >
                        {expandedId === visitor.id ? '收起' : '详情'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
