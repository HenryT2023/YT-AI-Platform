'use client';

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  FileJson,
  Save,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  History,
  Eye,
} from 'lucide-react';
import { policyApi, EvidenceGatePolicy, PolicyVersion } from '@/lib/api';

const POLICY_SCHEMA = {
  type: 'object',
  required: ['version', 'description', 'default_policy'],
  properties: {
    version: { type: 'string' },
    description: { type: 'string' },
    default_policy: {
      type: 'object',
      properties: {
        min_citations: { type: 'number' },
        min_score: { type: 'number' },
        max_soft_claims: { type: 'number' },
        strict_mode: { type: 'boolean' },
      },
    },
    site_policies: { type: 'object' },
    npc_policies: { type: 'object' },
    intent_overrides: { type: 'object' },
  },
};

export default function EvidenceGatePolicyPage() {
  const queryClient = useQueryClient();
  const [editedPolicy, setEditedPolicy] = useState<string>('');
  const [parseError, setParseError] = useState<string | null>(null);
  const [showVersions, setShowVersions] = useState(false);

  // 获取当前活跃策略
  const { data: activePolicy, isLoading } = useQuery({
    queryKey: ['activePolicy'],
    queryFn: async () => {
      const res = await policyApi.getActive();
      return res.data;
    },
  });

  // 获取版本列表
  const { data: versions } = useQuery({
    queryKey: ['policyVersions'],
    queryFn: async () => {
      const res = await policyApi.listVersions();
      return res.data;
    },
  });

  // 初始化编辑器内容
  useEffect(() => {
    if (activePolicy) {
      setEditedPolicy(JSON.stringify(activePolicy, null, 2));
    }
  }, [activePolicy]);

  // 保存新版本 mutation
  const saveMutation = useMutation({
    mutationFn: async (policy: EvidenceGatePolicy) => {
      const res = await policyApi.setActive(policy);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['activePolicy'] });
      queryClient.invalidateQueries({ queryKey: ['policyVersions'] });
      setParseError(null);
    },
    onError: (error: any) => {
      setParseError(error.response?.data?.detail || '保存失败');
    },
  });

  // 回滚 mutation
  const rollbackMutation = useMutation({
    mutationFn: async (version: string) => {
      const res = await policyApi.rollback(version);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['activePolicy'] });
      queryClient.invalidateQueries({ queryKey: ['policyVersions'] });
    },
  });

  const handleSave = () => {
    try {
      const parsed = JSON.parse(editedPolicy);
      
      // 基础 schema 校验
      if (!parsed.version || !parsed.description || !parsed.default_policy) {
        setParseError('缺少必填字段: version, description, default_policy');
        return;
      }
      
      // 自动更新版本号
      const currentVersion = activePolicy?.version || 'v0.0';
      const versionParts = currentVersion.replace('v', '').split('.');
      const newMinor = parseInt(versionParts[1] || '0') + 1;
      parsed.version = `v${versionParts[0]}.${newMinor}`;
      
      saveMutation.mutate(parsed);
    } catch (e: any) {
      setParseError(`JSON 解析错误: ${e.message}`);
    }
  };

  const handleRollback = (version: string) => {
    if (confirm(`确定要回滚到版本 ${version} 吗？`)) {
      rollbackMutation.mutate(version);
    }
  };

  const validateJson = (json: string): boolean => {
    try {
      const parsed = JSON.parse(json);
      if (!parsed.version || !parsed.description || !parsed.default_policy) {
        setParseError('缺少必填字段');
        return false;
      }
      setParseError(null);
      return true;
    } catch (e: any) {
      setParseError(`JSON 语法错误: ${e.message}`);
      return false;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <FileJson className="w-6 h-6" />
              Evidence Gate 策略管理
            </h1>
            <p className="text-gray-600 mt-1">
              管理证据闸门策略配置，控制 AI 回答的事实性要求
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowVersions(!showVersions)}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 flex items-center gap-2 border rounded-md"
            >
              <History className="w-4 h-4" />
              版本历史
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Editor */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow-sm">
              <div className="p-4 border-b flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-700">
                    当前版本:
                  </span>
                  <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-full">
                    {activePolicy?.version || '-'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      if (activePolicy) {
                        setEditedPolicy(JSON.stringify(activePolicy, null, 2));
                        setParseError(null);
                      }
                    }}
                    className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 flex items-center gap-1"
                  >
                    <RotateCcw className="w-4 h-4" />
                    重置
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={saveMutation.isPending || !!parseError}
                    className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1"
                  >
                    <Save className="w-4 h-4" />
                    {saveMutation.isPending ? '保存中...' : '保存为新版本'}
                  </button>
                </div>
              </div>

              {/* Error Banner */}
              {parseError && (
                <div className="p-3 bg-red-50 border-b border-red-100 flex items-center gap-2 text-red-700 text-sm">
                  <AlertCircle className="w-4 h-4" />
                  {parseError}
                </div>
              )}

              {/* Success Banner */}
              {saveMutation.isSuccess && (
                <div className="p-3 bg-green-50 border-b border-green-100 flex items-center gap-2 text-green-700 text-sm">
                  <CheckCircle2 className="w-4 h-4" />
                  策略已保存为新版本
                </div>
              )}

              {/* JSON Editor */}
              <div className="p-4">
                {isLoading ? (
                  <div className="h-96 flex items-center justify-center text-gray-500">
                    加载中...
                  </div>
                ) : (
                  <textarea
                    value={editedPolicy}
                    onChange={(e) => {
                      setEditedPolicy(e.target.value);
                      validateJson(e.target.value);
                    }}
                    className="w-full h-96 font-mono text-sm p-4 border rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="加载策略配置..."
                  />
                )}
              </div>
            </div>

            {/* Schema Reference */}
            <div className="mt-4 bg-white rounded-lg shadow-sm p-4">
              <h3 className="text-sm font-medium text-gray-700 mb-2">
                Schema 参考
              </h3>
              <div className="text-xs text-gray-600 font-mono bg-gray-50 p-3 rounded">
                <pre>{JSON.stringify(POLICY_SCHEMA, null, 2)}</pre>
              </div>
            </div>
          </div>

          {/* Version History */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-lg shadow-sm">
              <div className="p-4 border-b">
                <h3 className="text-sm font-medium text-gray-700">版本历史</h3>
              </div>
              <div className="divide-y max-h-[600px] overflow-y-auto">
                {versions?.length === 0 ? (
                  <div className="p-4 text-sm text-gray-500 text-center">
                    暂无版本记录
                  </div>
                ) : (
                  versions?.map((v) => (
                    <div
                      key={v.version}
                      className={`p-4 ${v.is_active ? 'bg-blue-50' : ''}`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium text-gray-900">
                          {v.version}
                        </span>
                        {v.is_active && (
                          <span className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs rounded-full">
                            当前
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 mb-2">
                        <div>操作人: {v.operator}</div>
                        <div>
                          时间: {format(new Date(v.created_at), 'yyyy-MM-dd HH:mm')}
                        </div>
                      </div>
                      {!v.is_active && (
                        <button
                          onClick={() => handleRollback(v.version)}
                          disabled={rollbackMutation.isPending}
                          className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
                        >
                          <RotateCcw className="w-3 h-3" />
                          回滚到此版本
                        </button>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Quick Actions */}
            <div className="mt-4 bg-white rounded-lg shadow-sm p-4">
              <h3 className="text-sm font-medium text-gray-700 mb-3">
                快速操作
              </h3>
              <div className="space-y-2">
                <button
                  onClick={() => {
                    const template = {
                      version: 'v1.0',
                      description: '新策略配置',
                      default_policy: {
                        min_citations: 1,
                        min_score: 0.3,
                        max_soft_claims: 2,
                        strict_mode: false,
                      },
                      site_policies: {},
                      npc_policies: {},
                      intent_overrides: {},
                    };
                    setEditedPolicy(JSON.stringify(template, null, 2));
                  }}
                  className="w-full px-3 py-2 text-sm text-left text-gray-700 hover:bg-gray-50 rounded-md"
                >
                  📝 使用默认模板
                </button>
                <button
                  onClick={() => {
                    const strict = {
                      ...JSON.parse(editedPolicy || '{}'),
                      default_policy: {
                        min_citations: 2,
                        min_score: 0.5,
                        max_soft_claims: 0,
                        strict_mode: true,
                      },
                    };
                    setEditedPolicy(JSON.stringify(strict, null, 2));
                  }}
                  className="w-full px-3 py-2 text-sm text-left text-gray-700 hover:bg-gray-50 rounded-md"
                >
                  🔒 切换到严格模式
                </button>
                <button
                  onClick={() => {
                    const relaxed = {
                      ...JSON.parse(editedPolicy || '{}'),
                      default_policy: {
                        min_citations: 0,
                        min_score: 0.2,
                        max_soft_claims: 5,
                        strict_mode: false,
                      },
                    };
                    setEditedPolicy(JSON.stringify(relaxed, null, 2));
                  }}
                  className="w-full px-3 py-2 text-sm text-left text-gray-700 hover:bg-gray-50 rounded-md"
                >
                  🌿 切换到宽松模式
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
