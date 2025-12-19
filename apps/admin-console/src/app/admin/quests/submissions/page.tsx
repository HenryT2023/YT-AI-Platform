'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  FileText,
  RefreshCw,
  Loader2,
  ChevronLeft,
  ChevronRight,
  Users,
  Target,
  CheckCircle,
  Clock,
  XCircle,
  ThumbsUp,
  ThumbsDown,
  X,
  TrendingUp,
} from 'lucide-react';

interface QuestSubmission {
  id: string;
  tenant_id: string;
  site_id: string;
  session_id: string;
  quest_id: string;
  proof_type: string;
  proof_payload: Record<string, any>;
  status: string;
  // v0.2.2 审核字段
  review_status: 'pending' | 'approved' | 'rejected';
  review_comment?: string | null;
  reviewed_at?: string | null;
  reviewed_by?: string | null;
  created_at: string;
  updated_at: string;
}

interface SubmissionListResponse {
  items: QuestSubmission[];
  total: number;
  limit: number;
  offset: number;
}

interface SubmissionStats {
  total_submissions: number;
  unique_sessions: number;
  unique_quests: number;
  status_breakdown: Record<string, number>;
  // v0.2.2 审核统计
  approved_count: number;
  rejected_count: number;
  pending_count: number;
  completion_rate: number;
}

// v0.2.2: 使用 review_status 而非 status
const REVIEW_STATUS_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  pending: { label: '待审核', color: 'bg-blue-100 text-blue-700', icon: Clock },
  approved: { label: '已通过', color: 'bg-green-100 text-green-700', icon: CheckCircle },
  rejected: { label: '未通过', color: 'bg-red-100 text-red-700', icon: XCircle },
};

// v0.2.3: 移除硬编码，tenant/site 由代理层从 Header 注入
// 前端不再需要传递这些参数

export default function QuestSubmissionsPage() {
  const [submissions, setSubmissions] = useState<QuestSubmission[]>([]);
  const [stats, setStats] = useState<SubmissionStats | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // 筛选和分页
  const [questIdFilter, setQuestIdFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const limit = 20;

  // v0.2.2 审核弹窗状态
  const [reviewModal, setReviewModal] = useState<{
    open: boolean;
    type: 'approve' | 'reject';
    submission: QuestSubmission | null;
  }>({ open: false, type: 'approve', submission: null });
  const [reviewComment, setReviewComment] = useState('');
  const [reviewing, setReviewing] = useState(false);

  const fetchSubmissions = async () => {
    setLoading(true);
    setError(null);
    try {
      // v0.2.3: tenant/site 由代理层从 Header 注入，前端只传业务参数
      const params = new URLSearchParams({
        limit: String(limit),
        offset: String((page - 1) * limit),
      });
      if (questIdFilter) params.set('quest_id', questIdFilter);
      if (statusFilter) params.set('status', statusFilter);

      const res = await fetch(`/api/admin/quest-submissions?${params}`);
      if (!res.ok) throw new Error('获取数据失败');
      const data: SubmissionListResponse = await res.json();
      setSubmissions(data.items || []);
      setTotal(data.total || 0);
    } catch (err: any) {
      setError(err.message || '获取任务提交列表失败');
      setSubmissions([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      // v0.2.3: tenant/site 由代理层从 Header 注入
      const res = await fetch(`/api/admin/quest-submissions/stats`);
      if (res.ok) {
        const data: SubmissionStats = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  };

  useEffect(() => {
    fetchSubmissions();
  }, [page, questIdFilter, statusFilter]);

  useEffect(() => {
    fetchStats();
  }, []);

  const totalPages = Math.ceil(total / limit);

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const truncateAnswer = (payload: Record<string, any>, maxLen = 50) => {
    const answer = payload?.answer;
    if (!answer) return '-';
    if (typeof answer !== 'string') return JSON.stringify(answer).slice(0, maxLen);
    return answer.length > maxLen ? answer.slice(0, maxLen) + '...' : answer;
  };

  // v0.2.2 审核操作
  const openReviewModal = (type: 'approve' | 'reject', submission: QuestSubmission) => {
    setReviewModal({ open: true, type, submission });
    setReviewComment('');
  };

  const closeReviewModal = () => {
    setReviewModal({ open: false, type: 'approve', submission: null });
    setReviewComment('');
  };

  const handleReview = async () => {
    if (!reviewModal.submission) return;
    
    setReviewing(true);
    try {
      const endpoint = reviewModal.type === 'approve' ? 'approve' : 'reject';
      const url = reviewComment 
        ? `/api/admin/quest-submissions/${reviewModal.submission.id}/${endpoint}?comment=${encodeURIComponent(reviewComment)}`
        : `/api/admin/quest-submissions/${reviewModal.submission.id}/${endpoint}`;
      const res = await fetch(url, {
        method: 'POST',
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || data.error || '操作失败');
      }
      
      closeReviewModal();
      fetchSubmissions();
      fetchStats();
    } catch (err: any) {
      const errMsg = typeof err === 'string' ? err : (err?.message || '审核操作失败');
      setError(errMsg);
    } finally {
      setReviewing(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
            <Link href="/admin/quests" className="hover:text-blue-600">
              任务管理
            </Link>
            <span>/</span>
            <span>提交记录</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">任务提交看板</h1>
          <p className="mt-1 text-sm text-gray-500">查看游客任务提交情况，评估任务设计效果</p>
        </div>
        <button
          onClick={() => { fetchSubmissions(); fetchStats(); }}
          className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* 统计卡片 */}
      {stats && (
        <div className="grid grid-cols-5 gap-4">
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                <FileText className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <div className="text-2xl font-bold text-gray-900">{stats.total_submissions}</div>
                <div className="text-sm text-gray-500">总提交数</div>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center">
                <Users className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <div className="text-2xl font-bold text-gray-900">{stats.unique_sessions}</div>
                <div className="text-sm text-gray-500">参与游客</div>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center">
                <Target className="w-5 h-5 text-amber-600" />
              </div>
              <div>
                <div className="text-2xl font-bold text-gray-900">{stats.unique_quests}</div>
                <div className="text-sm text-gray-500">涉及任务</div>
              </div>
            </div>
          </div>
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <div className="text-2xl font-bold text-gray-900">
                  {stats.approved_count || 0}
                </div>
                <div className="text-sm text-gray-500">已通过</div>
              </div>
            </div>
          </div>
          {/* v0.2.2 完成率 */}
          <div className="bg-white rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-indigo-600" />
              </div>
              <div>
                <div className="text-2xl font-bold text-gray-900">
                  {stats.completion_rate || 0}%
                </div>
                <div className="text-sm text-gray-500">完成率</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 筛选栏 */}
      <div className="flex items-center gap-4 bg-white rounded-lg shadow-sm border p-4">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">任务 ID:</label>
          <input
            type="text"
            value={questIdFilter}
            onChange={(e) => { setQuestIdFilter(e.target.value); setPage(1); }}
            placeholder="输入任务 ID"
            className="border rounded-md px-3 py-1.5 text-sm w-48"
          />
        </div>
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-600">状态:</label>
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className="border rounded-md px-3 py-1.5 text-sm"
          >
            <option value="">全部</option>
            <option value="submitted">待审核</option>
            <option value="approved">已通过</option>
            <option value="rejected">未通过</option>
          </select>
        </div>
        <div className="flex-1" />
        <span className="text-sm text-gray-500">
          共 {total} 条记录
        </span>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          {error}
        </div>
      )}

      {/* 提交列表 */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      ) : submissions.length === 0 ? (
        <div className="text-center py-12 text-gray-500 bg-white rounded-lg shadow-sm border">
          暂无提交记录
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">任务 ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">会话 ID</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">答案摘要</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">状态</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">提交时间</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {submissions.map((sub) => {
                const reviewConfig = REVIEW_STATUS_CONFIG[sub.review_status] || REVIEW_STATUS_CONFIG.pending;
                const StatusIcon = reviewConfig.icon;
                return (
                  <tr key={sub.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <span className="font-mono text-sm text-gray-900">{sub.quest_id}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs text-gray-500" title={sub.session_id}>
                        {sub.session_id.slice(0, 16)}...
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-gray-600" title={sub.proof_payload?.answer}>
                        {truncateAnswer(sub.proof_payload)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${reviewConfig.color}`}>
                        <StatusIcon className="w-3 h-3" />
                        {reviewConfig.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-gray-500">{formatDate(sub.created_at)}</span>
                    </td>
                    <td className="px-4 py-3">
                      {sub.review_status === 'pending' ? (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => openReviewModal('approve', sub)}
                            className="p-1.5 rounded hover:bg-green-100 text-green-600 transition-colors"
                            title="通过"
                          >
                            <ThumbsUp className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => openReviewModal('reject', sub)}
                            className="p-1.5 rounded hover:bg-red-100 text-red-600 transition-colors"
                            title="驳回"
                          >
                            <ThumbsDown className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-gray-400">已审核</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {/* 分页 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t bg-gray-50">
              <div className="text-sm text-gray-500">
                第 {page} / {totalPages} 页
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="p-1 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="p-1 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ChevronRight className="w-5 h-5" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* v0.2.2 审核弹窗 */}
      {reviewModal.open && reviewModal.submission && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <h3 className="text-lg font-semibold text-gray-900">
                {reviewModal.type === 'approve' ? '通过审核' : '驳回提交'}
              </h3>
              <button
                onClick={closeReviewModal}
                className="p-1 rounded hover:bg-gray-100 text-gray-400"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="px-6 py-4 space-y-4">
              <div>
                <div className="text-sm text-gray-500 mb-1">任务 ID</div>
                <div className="font-mono text-sm">{reviewModal.submission.quest_id}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500 mb-1">提交内容</div>
                <div className="text-sm bg-gray-50 rounded-lg p-3 max-h-32 overflow-y-auto">
                  {reviewModal.submission.proof_payload?.answer || '-'}
                </div>
              </div>
              <div>
                <label className="text-sm text-gray-500 mb-1 block">
                  {reviewModal.type === 'approve' ? '备注（可选）' : '驳回原因'}
                </label>
                <textarea
                  value={reviewComment}
                  onChange={(e) => setReviewComment(e.target.value)}
                  placeholder={reviewModal.type === 'approve' ? '输入备注...' : '请输入驳回原因...'}
                  className="w-full border rounded-lg px-3 py-2 text-sm resize-none h-20"
                  maxLength={500}
                />
              </div>
            </div>
            
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t bg-gray-50 rounded-b-xl">
              <button
                onClick={closeReviewModal}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
              >
                取消
              </button>
              <button
                onClick={handleReview}
                disabled={reviewing}
                className={`flex items-center gap-2 px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50 ${
                  reviewModal.type === 'approve'
                    ? 'bg-green-600 hover:bg-green-700'
                    : 'bg-red-600 hover:bg-red-700'
                }`}
              >
                {reviewing && <Loader2 className="w-4 h-4 animate-spin" />}
                {reviewModal.type === 'approve' ? '确认通过' : '确认驳回'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
