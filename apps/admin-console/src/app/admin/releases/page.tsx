'use client';

import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import {
  Package,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Play,
  RotateCcw,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Loader2,
} from 'lucide-react';

interface Release {
  id: string;
  tenant_id: string;
  site_id: string;
  name: string;
  description?: string;
  status: 'draft' | 'active' | 'archived';
  payload: Record<string, any>;
  created_by: string;
  created_at: string;
  activated_at?: string;
  archived_at?: string;
}

interface ValidationError {
  field: string;
  message: string;
  code: string;
}

interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
  warnings?: string[];
}

const STATUS_COLORS = {
  draft: 'bg-gray-100 text-gray-700',
  active: 'bg-green-100 text-green-700',
  archived: 'bg-yellow-100 text-yellow-700',
};

const STATUS_LABELS = {
  draft: '草稿',
  active: '活跃',
  archived: '已归档',
};

export default function ReleasesPage() {
  const [releases, setReleases] = useState<Release[]>([]);
  const [activeRelease, setActiveRelease] = useState<Release | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  
  // 操作状态
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [showValidationModal, setShowValidationModal] = useState(false);
  const [pendingAction, setPendingAction] = useState<{ type: 'activate' | 'rollback'; id: string } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const tenantId = 'yantian';
  const siteId = 'yantian-main';

  const fetchReleases = async () => {
    setLoading(true);
    try {
      let url = `/api/admin/releases?tenant_id=${tenantId}&site_id=${siteId}`;
      if (statusFilter !== 'all') {
        url += `&status=${statusFilter}`;
      }
      const res = await fetch(url);
      const data = await res.json();
      setReleases(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Failed to fetch releases:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchActiveRelease = async () => {
    try {
      const res = await fetch(`/api/admin/releases/active?tenant_id=${tenantId}&site_id=${siteId}`);
      const data = await res.json();
      setActiveRelease(data);
    } catch (error) {
      console.error('Failed to fetch active release:', error);
    }
  };

  useEffect(() => {
    fetchReleases();
    fetchActiveRelease();
  }, [statusFilter]);

  const handleValidate = async (id: string) => {
    setActionLoading(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/admin/releases/${id}/validate`, { method: 'POST' });
      const data = await res.json();
      setValidationResult(data);
      setShowValidationModal(true);
    } catch (error: any) {
      setActionError(error.message || '校验失败');
    } finally {
      setActionLoading(null);
    }
  };

  const handleActivate = async (id: string) => {
    setPendingAction({ type: 'activate', id });
    // 先校验
    setActionLoading(id);
    try {
      const res = await fetch(`/api/admin/releases/${id}/validate`, { method: 'POST' });
      const data = await res.json();
      setValidationResult(data);
      setShowValidationModal(true);
    } catch (error: any) {
      setActionError(error.message || '校验失败');
      setPendingAction(null);
    } finally {
      setActionLoading(null);
    }
  };

  const confirmActivate = async () => {
    if (!pendingAction || pendingAction.type !== 'activate') return;
    
    setActionLoading(pendingAction.id);
    setShowValidationModal(false);
    try {
      const res = await fetch(`/api/admin/releases/${pendingAction.id}/activate`, { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '激活失败');
      }
      await fetchReleases();
      await fetchActiveRelease();
    } catch (error: any) {
      setActionError(error.message || '激活失败');
    } finally {
      setActionLoading(null);
      setPendingAction(null);
    }
  };

  const handleRollback = async (id: string) => {
    if (!confirm('确定要回滚到此版本吗？当前活跃版本将被归档。')) return;
    
    setActionLoading(id);
    setActionError(null);
    try {
      const res = await fetch(`/api/admin/releases/${id}/rollback`, { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || '回滚失败');
      }
      await fetchReleases();
      await fetchActiveRelease();
    } catch (error: any) {
      setActionError(error.message || '回滚失败');
    } finally {
      setActionLoading(null);
    }
  };

  const formatPayloadSummary = (payload: Record<string, any>) => {
    const items = [];
    if (payload.prompts_active_map) {
      items.push(`${Object.keys(payload.prompts_active_map).length} 个 Prompt`);
    }
    if (payload.gate_policy_version) {
      items.push(`Gate v${payload.gate_policy_version}`);
    }
    if (payload.experiment_id) {
      items.push(`实验: ${payload.experiment_id}`);
    }
    return items.length > 0 ? items.join(' | ') : '无配置';
  };

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Release 管理</h1>
        <p className="text-gray-600 mt-1">管理灰度发布配置包</p>
      </div>

      {/* Active Release Card */}
      {activeRelease && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle className="w-5 h-5 text-green-600" />
            <span className="font-medium text-green-800">当前活跃版本</span>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <span className="text-lg font-semibold text-gray-900">{activeRelease.name}</span>
              <span className="text-gray-500 ml-2">({activeRelease.id.slice(0, 8)})</span>
            </div>
            <div className="text-sm text-gray-600">
              激活于 {activeRelease.activated_at ? format(new Date(activeRelease.activated_at), 'yyyy-MM-dd HH:mm') : '-'}
            </div>
          </div>
          <div className="text-sm text-gray-600 mt-1">
            {formatPayloadSummary(activeRelease.payload)}
          </div>
        </div>
      )}

      {/* Error Alert */}
      {actionError && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-center gap-2">
          <XCircle className="w-5 h-5 text-red-600" />
          <span className="text-red-800">{actionError}</span>
          <button onClick={() => setActionError(null)} className="ml-auto text-red-600 hover:text-red-800">
            ✕
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-4 mb-4">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm"
        >
          <option value="all">全部状态</option>
          <option value="draft">草稿</option>
          <option value="active">活跃</option>
          <option value="archived">已归档</option>
        </select>
        <button
          onClick={() => { fetchReleases(); fetchActiveRelease(); }}
          className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-900"
        >
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* Release List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
        </div>
      ) : releases.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          暂无 Release 记录
        </div>
      ) : (
        <div className="space-y-3">
          {releases.map((release) => (
            <div
              key={release.id}
              className="bg-white border rounded-lg shadow-sm overflow-hidden"
            >
              <div className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Package className="w-5 h-5 text-gray-400" />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900">{release.name}</span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[release.status]}`}>
                          {STATUS_LABELS[release.status]}
                        </span>
                      </div>
                      <div className="text-sm text-gray-500">
                        {release.id.slice(0, 8)} · 创建于 {format(new Date(release.created_at), 'yyyy-MM-dd HH:mm')}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {release.status === 'draft' && (
                      <>
                        <button
                          onClick={() => handleValidate(release.id)}
                          disabled={actionLoading === release.id}
                          className="px-3 py-1.5 text-sm border rounded-md hover:bg-gray-50 disabled:opacity-50"
                        >
                          校验
                        </button>
                        <button
                          onClick={() => handleActivate(release.id)}
                          disabled={actionLoading === release.id}
                          className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1"
                        >
                          {actionLoading === release.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Play className="w-4 h-4" />
                          )}
                          激活
                        </button>
                      </>
                    )}
                    {release.status === 'archived' && (
                      <button
                        onClick={() => handleRollback(release.id)}
                        disabled={actionLoading === release.id}
                        className="px-3 py-1.5 text-sm border border-orange-300 text-orange-600 rounded-md hover:bg-orange-50 disabled:opacity-50 flex items-center gap-1"
                      >
                        {actionLoading === release.id ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <RotateCcw className="w-4 h-4" />
                        )}
                        回滚
                      </button>
                    )}
                    <button
                      onClick={() => setExpandedId(expandedId === release.id ? null : release.id)}
                      className="p-1.5 text-gray-400 hover:text-gray-600"
                    >
                      {expandedId === release.id ? (
                        <ChevronUp className="w-5 h-5" />
                      ) : (
                        <ChevronDown className="w-5 h-5" />
                      )}
                    </button>
                  </div>
                </div>
                <div className="text-sm text-gray-600 mt-2">
                  {formatPayloadSummary(release.payload)}
                </div>
              </div>

              {/* Expanded Payload */}
              {expandedId === release.id && (
                <div className="border-t bg-gray-50 p-4">
                  <h4 className="text-sm font-medium text-gray-700 mb-2">Payload 详情</h4>
                  <pre className="text-xs bg-white border rounded p-3 overflow-auto max-h-64">
                    {JSON.stringify(release.payload, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Validation Modal */}
      {showValidationModal && validationResult && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-lg w-full mx-4">
            <div className="p-4 border-b">
              <div className="flex items-center gap-2">
                {validationResult.valid ? (
                  <CheckCircle className="w-5 h-5 text-green-600" />
                ) : (
                  <XCircle className="w-5 h-5 text-red-600" />
                )}
                <h3 className="text-lg font-medium">
                  {validationResult.valid ? '校验通过' : '校验失败'}
                </h3>
              </div>
            </div>
            <div className="p-4 max-h-96 overflow-auto">
              {validationResult.errors.length > 0 && (
                <div className="space-y-2">
                  {validationResult.errors.map((err, idx) => (
                    <div key={idx} className="flex items-start gap-2 text-sm">
                      <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
                      <div>
                        <span className="font-medium text-red-700">{err.field}</span>
                        <span className="text-gray-600">: {err.message}</span>
                        <span className="text-gray-400 ml-1">({err.code})</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {validationResult.warnings && validationResult.warnings.length > 0 && (
                <div className="mt-4 space-y-2">
                  <h4 className="text-sm font-medium text-yellow-700">警告</h4>
                  {validationResult.warnings.map((warn, idx) => (
                    <div key={idx} className="text-sm text-yellow-600">{warn}</div>
                  ))}
                </div>
              )}
              {validationResult.valid && validationResult.errors.length === 0 && (
                <p className="text-green-600">所有校验项通过，可以安全激活。</p>
              )}
            </div>
            <div className="p-4 border-t flex justify-end gap-2">
              <button
                onClick={() => { setShowValidationModal(false); setPendingAction(null); }}
                className="px-4 py-2 text-sm border rounded-md hover:bg-gray-50"
              >
                关闭
              </button>
              {pendingAction?.type === 'activate' && validationResult.valid && (
                <button
                  onClick={confirmActivate}
                  className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
                >
                  确认激活
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
