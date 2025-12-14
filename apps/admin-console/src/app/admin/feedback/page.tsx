'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format, formatDistanceToNow } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import {
  AlertCircle,
  Clock,
  CheckCircle2,
  XCircle,
  User,
  Filter,
  RefreshCw,
  ChevronDown,
} from 'lucide-react';
import { feedbackApi, Feedback, FeedbackStats } from '@/lib/api';

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待处理' },
  { value: 'triaged', label: '已分派' },
  { value: 'in_progress', label: '处理中' },
  { value: 'resolved', label: '已解决' },
  { value: 'closed', label: '已关闭' },
];

const SEVERITY_OPTIONS = [
  { value: '', label: '全部严重度' },
  { value: 'critical', label: '严重' },
  { value: 'high', label: '高' },
  { value: 'medium', label: '中' },
  { value: 'low', label: '低' },
];

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  triaged: 'bg-blue-100 text-blue-800',
  in_progress: 'bg-purple-100 text-purple-800',
  resolved: 'bg-green-100 text-green-800',
  closed: 'bg-gray-100 text-gray-800',
};

const SEVERITY_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-800',
  high: 'bg-orange-100 text-orange-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-gray-100 text-gray-800',
};

export default function FeedbackPage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [selectedFeedback, setSelectedFeedback] = useState<Feedback | null>(null);
  const [showTriageModal, setShowTriageModal] = useState(false);
  const [showStatusModal, setShowStatusModal] = useState(false);

  // 获取反馈列表
  const { data: feedbacks, isLoading, refetch } = useQuery({
    queryKey: ['feedbacks', statusFilter, severityFilter, overdueOnly],
    queryFn: async () => {
      const params: any = { limit: 100 };
      if (statusFilter) params.status = statusFilter;
      if (severityFilter) params.severity = severityFilter;
      if (overdueOnly) params.overdue_only = true;
      const res = await feedbackApi.list(params);
      // 处理分页格式或直接数组格式
      const data = res.data;
      if (Array.isArray(data)) {
        return data;
      }
      // 如果是分页格式 {items: [], total: number}
      if (data && Array.isArray(data.items)) {
        return data.items;
      }
      return [];
    },
  });

  // 获取统计数据
  const { data: stats } = useQuery({
    queryKey: ['feedbackStats'],
    queryFn: async () => {
      const res = await feedbackApi.stats();
      return res.data;
    },
  });

  // 分派 mutation
  const triageMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: any }) => {
      const res = await feedbackApi.triage(id, data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feedbacks'] });
      queryClient.invalidateQueries({ queryKey: ['feedbackStats'] });
      setShowTriageModal(false);
      setSelectedFeedback(null);
    },
  });

  // 状态更新 mutation
  const statusMutation = useMutation({
    mutationFn: async ({ id, data }: { id: string; data: any }) => {
      const res = await feedbackApi.updateStatus(id, data);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feedbacks'] });
      queryClient.invalidateQueries({ queryKey: ['feedbackStats'] });
      setShowStatusModal(false);
      setSelectedFeedback(null);
    },
  });

  const handleTriage = (feedback: Feedback) => {
    setSelectedFeedback(feedback);
    setShowTriageModal(true);
  };

  const handleStatusUpdate = (feedback: Feedback) => {
    setSelectedFeedback(feedback);
    setShowStatusModal(true);
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">反馈工单管理</h1>
          <p className="text-gray-600 mt-1">管理用户反馈，跟踪处理进度</p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          <StatCard
            title="待处理"
            value={stats?.by_status?.pending || 0}
            icon={<Clock className="w-5 h-5 text-yellow-600" />}
            color="yellow"
          />
          <StatCard
            title="处理中"
            value={(stats?.by_status?.triaged || 0) + (stats?.by_status?.in_progress || 0)}
            icon={<RefreshCw className="w-5 h-5 text-blue-600" />}
            color="blue"
          />
          <StatCard
            title="已逾期"
            value={stats?.overdue_count || 0}
            icon={<AlertCircle className="w-5 h-5 text-red-600" />}
            color="red"
            highlight={!!stats?.overdue_count}
          />
          <StatCard
            title="平均解决时间"
            value={stats?.avg_time_to_resolve_hours ? `${stats.avg_time_to_resolve_hours.toFixed(1)}h` : '-'}
            icon={<CheckCircle2 className="w-5 h-5 text-green-600" />}
            color="green"
          />
        </div>

        {/* Filters */}
        <div className="bg-white rounded-lg shadow-sm p-4 mb-6">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-gray-500" />
              <span className="text-sm text-gray-600">筛选：</span>
            </div>
            
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-1.5 border rounded-md text-sm"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="px-3 py-1.5 border rounded-md text-sm"
            >
              {SEVERITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={overdueOnly}
                onChange={(e) => setOverdueOnly(e.target.checked)}
                className="rounded"
              />
              仅显示逾期
            </label>

            <button
              onClick={() => refetch()}
              className="ml-auto px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 flex items-center gap-1"
            >
              <RefreshCw className="w-4 h-4" />
              刷新
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="bg-white rounded-lg shadow-sm overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">类型</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">严重度</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">状态</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">负责人</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">SLA</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">创建时间</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">操作</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                    加载中...
                  </td>
                </tr>
              ) : feedbacks?.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-gray-500">
                    暂无数据
                  </td>
                </tr>
              ) : (
                feedbacks?.map((fb) => (
                  <tr key={fb.id} className={fb.overdue_flag ? 'bg-red-50' : ''}>
                    <td className="px-4 py-3 text-sm font-mono text-gray-600">
                      {fb.id.slice(0, 8)}...
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {fb.feedback_type}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 text-xs rounded-full ${SEVERITY_COLORS[fb.severity] || 'bg-gray-100'}`}>
                        {fb.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-1 text-xs rounded-full ${STATUS_COLORS[fb.status] || 'bg-gray-100'}`}>
                        {fb.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {fb.assignee || '-'}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {fb.sla_due_at ? (
                        <span className={fb.overdue_flag ? 'text-red-600 font-medium' : 'text-gray-600'}>
                          {fb.overdue_flag && <AlertCircle className="w-3 h-3 inline mr-1" />}
                          {formatDistanceToNow(new Date(fb.sla_due_at), { locale: zhCN, addSuffix: true })}
                        </span>
                      ) : (
                        '-'
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {format(new Date(fb.created_at), 'MM-dd HH:mm')}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <div className="flex gap-2">
                        {fb.status === 'pending' && (
                          <button
                            onClick={() => handleTriage(fb)}
                            className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700"
                          >
                            分派
                          </button>
                        )}
                        {['triaged', 'in_progress'].includes(fb.status) && (
                          <button
                            onClick={() => handleStatusUpdate(fb)}
                            className="px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700"
                          >
                            推进
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Triage Modal */}
        {showTriageModal && selectedFeedback && (
          <TriageModal
            feedback={selectedFeedback}
            onClose={() => {
              setShowTriageModal(false);
              setSelectedFeedback(null);
            }}
            onSubmit={(data) => {
              triageMutation.mutate({ id: selectedFeedback.id, data });
            }}
            isLoading={triageMutation.isPending}
          />
        )}

        {/* Status Update Modal */}
        {showStatusModal && selectedFeedback && (
          <StatusModal
            feedback={selectedFeedback}
            onClose={() => {
              setShowStatusModal(false);
              setSelectedFeedback(null);
            }}
            onSubmit={(data) => {
              statusMutation.mutate({ id: selectedFeedback.id, data });
            }}
            isLoading={statusMutation.isPending}
          />
        )}
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  icon,
  color,
  highlight,
}: {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  color: string;
  highlight?: boolean;
}) {
  return (
    <div className={`bg-white rounded-lg shadow-sm p-4 ${highlight ? 'ring-2 ring-red-500' : ''}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-600">{title}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
        </div>
        <div className={`p-2 rounded-full bg-${color}-100`}>{icon}</div>
      </div>
    </div>
  );
}

function TriageModal({
  feedback,
  onClose,
  onSubmit,
  isLoading,
}: {
  feedback: Feedback;
  onClose: () => void;
  onSubmit: (data: any) => void;
  isLoading: boolean;
}) {
  const [assignee, setAssignee] = useState('');
  const [groupName, setGroupName] = useState('');
  const [slaHours, setSlaHours] = useState(24);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 className="text-lg font-semibold mb-4">分派工单</h3>
        <p className="text-sm text-gray-600 mb-4">
          工单 ID: {feedback.id.slice(0, 8)}... | 类型: {feedback.feedback_type}
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              负责人
            </label>
            <input
              type="text"
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              placeholder="输入负责人名称"
              className="w-full px-3 py-2 border rounded-md"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              分组
            </label>
            <select
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              className="w-full px-3 py-2 border rounded-md"
            >
              <option value="">选择分组</option>
              <option value="content_team">内容团队</option>
              <option value="tech_team">技术团队</option>
              <option value="ops_team">运营团队</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              SLA (小时)
            </label>
            <input
              type="number"
              value={slaHours}
              onChange={(e) => setSlaHours(Number(e.target.value))}
              min={1}
              max={168}
              className="w-full px-3 py-2 border rounded-md"
            />
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
          >
            取消
          </button>
          <button
            onClick={() => onSubmit({ assignee, group_name: groupName, sla_hours: slaHours })}
            disabled={isLoading}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {isLoading ? '提交中...' : '确认分派'}
          </button>
        </div>
      </div>
    </div>
  );
}

function StatusModal({
  feedback,
  onClose,
  onSubmit,
  isLoading,
}: {
  feedback: Feedback;
  onClose: () => void;
  onSubmit: (data: any) => void;
  isLoading: boolean;
}) {
  const [status, setStatus] = useState('');
  const [resolutionNote, setResolutionNote] = useState('');

  const nextStatuses = {
    triaged: ['in_progress'],
    in_progress: ['resolved', 'closed'],
  };

  const availableStatuses = nextStatuses[feedback.status as keyof typeof nextStatuses] || [];

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 className="text-lg font-semibold mb-4">推进状态</h3>
        <p className="text-sm text-gray-600 mb-4">
          当前状态: <span className={`px-2 py-1 text-xs rounded-full ${STATUS_COLORS[feedback.status]}`}>{feedback.status}</span>
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              新状态
            </label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full px-3 py-2 border rounded-md"
            >
              <option value="">选择新状态</option>
              {availableStatuses.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          {['resolved', 'closed'].includes(status) && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                解决说明
              </label>
              <textarea
                value={resolutionNote}
                onChange={(e) => setResolutionNote(e.target.value)}
                placeholder="描述解决方案..."
                rows={3}
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
          >
            取消
          </button>
          <button
            onClick={() => onSubmit({ status, resolution_note: resolutionNote })}
            disabled={isLoading || !status}
            className="px-4 py-2 text-sm bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
          >
            {isLoading ? '提交中...' : '确认推进'}
          </button>
        </div>
      </div>
    </div>
  );
}
