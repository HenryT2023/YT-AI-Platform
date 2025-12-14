'use client';

import { useState } from 'react';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import {
  Settings,
  Database,
  Globe,
  Bell,
  Shield,
  Palette,
  Save,
  RefreshCw,
} from 'lucide-react';

interface SettingSection {
  id: string;
  title: string;
  description: string;
  icon: React.ElementType;
  settings: SettingItem[];
}

interface SettingItem {
  key: string;
  label: string;
  type: 'text' | 'toggle' | 'select' | 'number';
  value: any;
  options?: { value: string; label: string }[];
  description?: string;
}

const SETTING_SECTIONS: SettingSection[] = [
  {
    id: 'general',
    title: '基础设置',
    description: '站点基本信息配置',
    icon: Globe,
    settings: [
      { key: 'site_name', label: '站点名称', type: 'text', value: '严田古村', description: '显示在前端的站点名称' },
      { key: 'site_id', label: '站点 ID', type: 'text', value: 'yantian-main', description: '系统内部使用的站点标识' },
      { key: 'default_language', label: '默认语言', type: 'select', value: 'zh-CN', options: [
        { value: 'zh-CN', label: '简体中文' },
        { value: 'en-US', label: 'English' },
      ]},
    ],
  },
  {
    id: 'ai',
    title: 'AI 配置',
    description: 'AI 对话与生成相关设置',
    icon: Database,
    settings: [
      { key: 'llm_provider', label: 'LLM 服务商', type: 'select', value: 'aliyun', options: [
        { value: 'aliyun', label: '阿里云通义' },
        { value: 'openai', label: 'OpenAI' },
        { value: 'azure', label: 'Azure OpenAI' },
      ]},
      { key: 'max_tokens', label: '最大 Token 数', type: 'number', value: 2048 },
      { key: 'temperature', label: '温度参数', type: 'number', value: 0.7 },
      { key: 'enable_streaming', label: '启用流式输出', type: 'toggle', value: true },
    ],
  },
  {
    id: 'notifications',
    title: '通知设置',
    description: '告警与通知渠道配置',
    icon: Bell,
    settings: [
      { key: 'webhook_enabled', label: '启用 Webhook', type: 'toggle', value: true },
      { key: 'webhook_url', label: 'Webhook URL', type: 'text', value: '' },
      { key: 'email_notifications', label: '邮件通知', type: 'toggle', value: false },
    ],
  },
  {
    id: 'security',
    title: '安全设置',
    description: '访问控制与安全策略',
    icon: Shield,
    settings: [
      { key: 'rate_limit_enabled', label: '启用限流', type: 'toggle', value: true },
      { key: 'rate_limit_rpm', label: '每分钟请求限制', type: 'number', value: 60 },
      { key: 'content_filter_enabled', label: '内容过滤', type: 'toggle', value: true },
    ],
  },
];

export default function SettingsPage() {
  const [sections, setSections] = useState(SETTING_SECTIONS);
  const [activeSection, setActiveSection] = useState('general');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSettingChange = (sectionId: string, key: string, value: any) => {
    setSections(prev => prev.map(section => {
      if (section.id !== sectionId) return section;
      return {
        ...section,
        settings: section.settings.map(s => s.key === key ? { ...s, value } : s),
      };
    }));
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    // 模拟保存
    await new Promise(resolve => setTimeout(resolve, 1000));
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  const currentSection = sections.find(s => s.id === activeSection);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">系统设置</h1>
            <p className="mt-1 text-sm text-gray-500">管理系统配置项</p>
          </div>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50"
          >
            {saving ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saving ? '保存中...' : '保存设置'}
          </button>
        </div>

        {saved && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-3 text-green-700 text-sm">
            设置已保存（演示模式，实际未持久化）
          </div>
        )}

        <div className="flex gap-6">
          {/* 侧边导航 */}
          <div className="w-48 space-y-1">
            {sections.map(section => {
              const Icon = section.icon;
              return (
                <button
                  key={section.id}
                  onClick={() => setActiveSection(section.id)}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                    activeSection === section.id
                      ? 'bg-primary-50 text-primary-700'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {section.title}
                </button>
              );
            })}
          </div>

          {/* 设置内容 */}
          <div className="flex-1 bg-white border rounded-lg p-6">
            {currentSection && (
              <>
                <div className="mb-6">
                  <h2 className="text-lg font-semibold text-gray-900">{currentSection.title}</h2>
                  <p className="text-sm text-gray-500">{currentSection.description}</p>
                </div>

                <div className="space-y-6">
                  {currentSection.settings.map(setting => (
                    <div key={setting.key} className="flex items-start justify-between">
                      <div className="flex-1">
                        <label className="block text-sm font-medium text-gray-700">
                          {setting.label}
                        </label>
                        {setting.description && (
                          <p className="text-xs text-gray-500 mt-0.5">{setting.description}</p>
                        )}
                      </div>
                      <div className="ml-4 w-64">
                        {setting.type === 'text' && (
                          <input
                            type="text"
                            value={setting.value}
                            onChange={(e) => handleSettingChange(currentSection.id, setting.key, e.target.value)}
                            className="w-full border rounded-md px-3 py-2 text-sm"
                          />
                        )}
                        {setting.type === 'number' && (
                          <input
                            type="number"
                            value={setting.value}
                            onChange={(e) => handleSettingChange(currentSection.id, setting.key, parseFloat(e.target.value))}
                            className="w-full border rounded-md px-3 py-2 text-sm"
                          />
                        )}
                        {setting.type === 'select' && (
                          <select
                            value={setting.value}
                            onChange={(e) => handleSettingChange(currentSection.id, setting.key, e.target.value)}
                            className="w-full border rounded-md px-3 py-2 text-sm"
                          >
                            {setting.options?.map(opt => (
                              <option key={opt.value} value={opt.value}>{opt.label}</option>
                            ))}
                          </select>
                        )}
                        {setting.type === 'toggle' && (
                          <button
                            onClick={() => handleSettingChange(currentSection.id, setting.key, !setting.value)}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                              setting.value ? 'bg-primary-600' : 'bg-gray-200'
                            }`}
                          >
                            <span
                              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                setting.value ? 'translate-x-6' : 'translate-x-1'
                              }`}
                            />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
