'use client';

import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import {
  Bell,
  BellOff,
  AlertTriangle,
  AlertCircle,
  Info,
  ChevronDown,
  ChevronUp,
  Plus,
  Trash2,
  Play,
  RefreshCw,
  Loader2,
  X,
} from 'lucide-react';

interface AlertEvent {
  id: string;
  tenant_id: string;
  site_id?: string;
  alert_code: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  status: 'firing' | 'resolved';
  window: string;
  current_value?: number;
  threshold?: number;
  condition?: string;
  unit?: string;
  dedup_key: string;
  first_seen_at: string;
  last_seen_at: string;
  resolved_at?: string;
  context: Record<string, any>;
  webhook_sent?: string;
}

interface AlertSilence {
  id: string;
  tenant_id: string;
  site_id?: string;
  alert_code?: string;
  severity?: string;
  starts_at: string;
  ends_at: string;
  reason?: string;
  created_by: string;
  created_at: string;
}

interface AlertRule {
  code: string;
  name: string;
  category: string;
  severity: string;
  description: string;
}

const SEVERITY_COLORS = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  high: 'bg-orange-100 text-orange-700 border-orange-200',
  medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  low: 'bg-blue-100 text-blue-700 border-blue-200',
};

const SEVERITY_ICONS = {
  critical: AlertCircle,
  high: AlertTriangle,
  medium: AlertTriangle,
  low: Info,
};

export default function AlertsPage() {
  const [activeTab, setActiveTab] = useState<'events' | 'silences'>('events');
  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [silences, setSilences] = useState<AlertSilence[]>([]);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  
  // Filters
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('firing');
  
  // Create silence modal
  const [showCreateSilence, setShowCreateSilence] = useState(false);
  const [silenceForm, setSilenceForm] = useState({
    alert_code: '',
    duration_minutes: 60,
    reason: '',
  });
  
  // Action states
  const [actionLoading, setActionLoading] = useState(false);
  const [evaluateResult, setEvaluateResult] = useState<any>(null);

  // v0.2.4: tenant/site 由代理层从 Header 注入

  const fetchEvents = async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter !== 'all') {
        params.set('status', statusFilter);
      }
      if (severityFilter !== 'all') {
        params.set('severity', severityFilter);
      }
      const url = `/api/admin/alerts/events${params.toString() ? '?' + params.toString() : ''}`;
      const res = await fetch(url);
      const data = await res.json();
      setEvents(data.items || []);
    } catch (error) {
      console.error('Failed to fetch events:', error);
    }
  };

  const fetchSilences = async () => {
    try {
      const res = await fetch(`/api/admin/alerts/silences?active_only=true`);
      const data = await res.json();
      setSilences(data.items || []);
    } catch (error) {
      console.error('Failed to fetch silences:', error);
    }
  };

  const fetchRules = async () => {
    try {
      const res = await fetch('/api/admin/alerts/rules');
      const data = await res.json();
      setRules(data.rules || []);
    } catch (error) {
      console.error('Failed to fetch rules:', error);
    }
  };

  const fetchAll = async () => {
    setLoading(true);
    await Promise.all([fetchEvents(), fetchSilences(), fetchRules()]);
    setLoading(false);
  };

  useEffect(() => {
    fetchAll();
  }, []);

  useEffect(() => {
    if (!loading) {
      fetchEvents();
    }
  }, [severityFilter, statusFilter]);

  const handleEvaluate = async () => {
    setActionLoading(true);
    setEvaluateResult(null);
    try {
      const res = await fetch(`/api/admin/alerts/evaluate`, {
        method: 'POST',
      });
      const data = await res.json();
      setEvaluateResult(data);
      await fetchEvents();
    } catch (error: any) {
      setEvaluateResult({ error: error.message });
    } finally {
      setActionLoading(false);
    }
  };

  const handleCreateSilence = async () => {
    setActionLoading(true);
    try {
      const res = await fetch('/api/admin/alerts/silences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          alert_code: silenceForm.alert_code || undefined,
          duration_minutes: silenceForm.duration_minutes,
          reason: silenceForm.reason || undefined,
        }),
      });
      if (res.ok) {
        setShowCreateSilence(false);
        setSilenceForm({ alert_code: '', duration_minutes: 60, reason: '' });
        await fetchSilences();
      }
    } catch (error) {
      console.error('Failed to create silence:', error);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteSilence = async (id: string) => {
    if (!confirm('确定要删除此静默规则吗？')) return;
    try {
      await fetch(`/api/admin/alerts/silences/${id}`, { method: 'DELETE' });
      await fetchSilences();
    } catch (error) {
      console.error('Failed to delete silence:', error);
    }
  };

  const formatAlertName = (code: string) => {
    const rule = rules.find(r => r.code === code);
    return rule?.name || code;
  };

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">告警管理</h1>
        <p className="text-gray-600 mt-1">监控系统告警事件与静默规则</p>
      </div>

      {/* Actions Bar */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('events')}
            className={`px-4 py-2 text-sm font-medium rounded-md ${
              activeTab === 'events'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 border hover:bg-gray-50'
            }`}
          >
            <Bell className="w-4 h-4 inline mr-1" />
            告警事件
          </button>
          <button
            onClick={() => setActiveTab('silences')}
            className={`px-4 py-2 text-sm font-medium rounded-md ${
              activeTab === 'silences'
                ? 'bg-blue-600 text-white'
                : 'bg-white text-gray-700 border hover:bg-gray-50'
            }`}
          >
            <BellOff className="w-4 h-4 inline mr-1" />
            静默规则 ({silences.length})
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleEvaluate}
            disabled={actionLoading}
            className="flex items-center gap-1 px-3 py-2 text-sm bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
          >
            {actionLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            立即评估
          </button>
          <button
            onClick={fetchAll}
            className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-900"
          >
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* Evaluate Result */}
      {evaluateResult && (
        <div className={`mb-4 p-4 rounded-lg ${evaluateResult.error ? 'bg-red-50 border border-red-200' : 'bg-green-50 border border-green-200'}`}>
          <div className="flex items-center justify-between">
            <div>
              {evaluateResult.error ? (
                <span className="text-red-700">评估失败: {evaluateResult.error}</span>
              ) : (
                <span className="text-green-700">
                  评估完成: {evaluateResult.new_events_count || 0} 个新事件, 
                  {evaluateResult.resolved_count || 0} 个已解决,
                  {evaluateResult.webhook_sent_count || 0} 个通知已发送
                </span>
              )}
            </div>
            <button onClick={() => setEvaluateResult(null)} className="text-gray-400 hover:text-gray-600">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Events Tab */}
      {activeTab === 'events' && (
        <div>
          {/* Filters */}
          <div className="flex items-center gap-4 mb-4">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="border rounded-md px-3 py-2 text-sm"
            >
              <option value="all">全部状态</option>
              <option value="firing">触发中</option>
              <option value="resolved">已解决</option>
            </select>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="border rounded-md px-3 py-2 text-sm"
            >
              <option value="all">全部级别</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>

          {/* Events List */}
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
            </div>
          ) : events.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              暂无告警事件
            </div>
          ) : (
            <div className="space-y-3">
              {events.map((event) => {
                const SeverityIcon = SEVERITY_ICONS[event.severity];
                return (
                  <div
                    key={event.id}
                    className={`bg-white border rounded-lg shadow-sm overflow-hidden ${
                      event.status === 'resolved' ? 'opacity-60' : ''
                    }`}
                  >
                    <div className="p-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <SeverityIcon className={`w-5 h-5 ${
                            event.severity === 'critical' ? 'text-red-500' :
                            event.severity === 'high' ? 'text-orange-500' :
                            event.severity === 'medium' ? 'text-yellow-500' : 'text-blue-500'
                          }`} />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-gray-900">
                                {formatAlertName(event.alert_code)}
                              </span>
                              <span className={`px-2 py-0.5 rounded text-xs font-medium border ${SEVERITY_COLORS[event.severity]}`}>
                                {event.severity}
                              </span>
                              {event.status === 'resolved' && (
                                <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
                                  已解决
                                </span>
                              )}
                            </div>
                            <div className="text-sm text-gray-500">
                              {event.alert_code} · 首次触发 {format(new Date(event.first_seen_at), 'MM-dd HH:mm')}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {event.current_value !== undefined && (
                            <span className="text-sm text-gray-600">
                              当前值: {event.current_value}{event.unit || ''}
                              {event.threshold !== undefined && ` (阈值: ${event.condition || ''} ${event.threshold})`}
                            </span>
                          )}
                          <button
                            onClick={() => setExpandedId(expandedId === event.id ? null : event.id)}
                            className="p-1.5 text-gray-400 hover:text-gray-600"
                          >
                            {expandedId === event.id ? (
                              <ChevronUp className="w-5 h-5" />
                            ) : (
                              <ChevronDown className="w-5 h-5" />
                            )}
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Expanded Context */}
                    {expandedId === event.id && (
                      <div className="border-t bg-gray-50 p-4">
                        <h4 className="text-sm font-medium text-gray-700 mb-2">上下文信息</h4>
                        <div className="grid grid-cols-2 gap-4 text-sm">
                          <div>
                            <span className="text-gray-500">Dedup Key:</span>
                            <span className="ml-2 font-mono text-xs">{event.dedup_key}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">最后触发:</span>
                            <span className="ml-2">{format(new Date(event.last_seen_at), 'yyyy-MM-dd HH:mm:ss')}</span>
                          </div>
                          {event.context.active_release_id && (
                            <div>
                              <span className="text-gray-500">Release ID:</span>
                              <span className="ml-2 font-mono text-xs">{event.context.active_release_id}</span>
                            </div>
                          )}
                          {event.webhook_sent && (
                            <div>
                              <span className="text-gray-500">Webhook:</span>
                              <span className="ml-2">{event.webhook_sent}</span>
                            </div>
                          )}
                        </div>
                        {event.context.metrics_snapshot && (
                          <div className="mt-3">
                            <h5 className="text-sm font-medium text-gray-700 mb-1">指标快照</h5>
                            <pre className="text-xs bg-white border rounded p-2 overflow-auto max-h-32">
                              {JSON.stringify(event.context.metrics_snapshot, null, 2)}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Silences Tab */}
      {activeTab === 'silences' && (
        <div>
          <div className="mb-4">
            <button
              onClick={() => setShowCreateSilence(true)}
              className="flex items-center gap-1 px-3 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              <Plus className="w-4 h-4" />
              创建静默
            </button>
          </div>

          {silences.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              暂无活跃的静默规则
            </div>
          ) : (
            <div className="space-y-3">
              {silences.map((silence) => (
                <div key={silence.id} className="bg-white border rounded-lg shadow-sm p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <BellOff className="w-5 h-5 text-gray-400" />
                      <div>
                        <div className="font-medium text-gray-900">
                          {silence.alert_code ? formatAlertName(silence.alert_code) : '全部告警'}
                          {silence.severity && ` (${silence.severity})`}
                        </div>
                        <div className="text-sm text-gray-500">
                          {format(new Date(silence.starts_at), 'MM-dd HH:mm')} ~ {format(new Date(silence.ends_at), 'MM-dd HH:mm')}
                        </div>
                        {silence.reason && (
                          <div className="text-sm text-gray-600 mt-1">原因: {silence.reason}</div>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteSilence(silence.id)}
                      className="p-2 text-red-500 hover:text-red-700 hover:bg-red-50 rounded"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Create Silence Modal */}
      {showCreateSilence && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4">
            <div className="p-4 border-b">
              <h3 className="text-lg font-medium">创建静默规则</h3>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  告警代码 (留空表示全部)
                </label>
                <select
                  value={silenceForm.alert_code}
                  onChange={(e) => setSilenceForm({ ...silenceForm, alert_code: e.target.value })}
                  className="w-full border rounded-md px-3 py-2 text-sm"
                >
                  <option value="">全部告警</option>
                  {rules.map((rule) => (
                    <option key={rule.code} value={rule.code}>
                      {rule.name} ({rule.code})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  持续时间 (分钟)
                </label>
                <input
                  type="number"
                  value={silenceForm.duration_minutes}
                  onChange={(e) => setSilenceForm({ ...silenceForm, duration_minutes: parseInt(e.target.value) || 60 })}
                  className="w-full border rounded-md px-3 py-2 text-sm"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  原因
                </label>
                <textarea
                  value={silenceForm.reason}
                  onChange={(e) => setSilenceForm({ ...silenceForm, reason: e.target.value })}
                  className="w-full border rounded-md px-3 py-2 text-sm"
                  rows={2}
                  placeholder="可选，说明静默原因"
                />
              </div>
            </div>
            <div className="p-4 border-t flex justify-end gap-2">
              <button
                onClick={() => setShowCreateSilence(false)}
                className="px-4 py-2 text-sm border rounded-md hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={handleCreateSilence}
                disabled={actionLoading}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
              >
                {actionLoading ? '创建中...' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
