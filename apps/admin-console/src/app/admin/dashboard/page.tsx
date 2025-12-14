'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import {
  Users,
  MessageSquare,
  Map,
  Target,
  TrendingUp,
  Activity,
  LogOut,
} from 'lucide-react';

interface UserInfo {
  id: string;
  username: string;
  display_name?: string;
  role: string;
}

export default function AdminDashboard() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);

  useEffect(() => {
    fetch('/api/auth/me')
      .then((res) => {
        if (!res.ok) throw new Error('未登录');
        return res.json();
      })
      .then(setUser)
      .catch(() => {
        // 未登录，跳转到登录页
        router.push('/login');
      });
  }, [router]);

  const handleLogout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
  };

  const stats = [
    { label: 'NPC 角色', value: '-', icon: Users, color: 'bg-blue-500' },
    { label: '场景数量', value: '-', icon: Map, color: 'bg-green-500' },
    { label: '任务配置', value: '-', icon: Target, color: 'bg-purple-500' },
    { label: '今日对话', value: '-', icon: MessageSquare, color: 'bg-orange-500' },
  ];

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">管理后台</h1>
            <p className="mt-1 text-sm text-gray-500">
              欢迎回来，{user?.display_name || user?.username || '管理员'}
              {user?.role && (
                <span className="ml-2 px-2 py-0.5 bg-primary-100 text-primary-700 rounded text-xs">
                  {user.role}
                </span>
              )}
            </p>
          </div>
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 px-4 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
            退出登录
          </button>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {stats.map((stat) => (
            <div
              key={stat.label}
              className="bg-white rounded-xl shadow-sm border p-6"
            >
              <div className="flex items-center gap-4">
                <div className={`p-3 rounded-lg ${stat.color}`}>
                  <stat.icon className="w-6 h-6 text-white" />
                </div>
                <div>
                  <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
                  <p className="text-sm text-gray-500">{stat.label}</p>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Quick Actions */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">快捷操作</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <a
              href="/admin/npcs"
              className="flex flex-col items-center gap-2 p-4 rounded-lg border hover:bg-gray-50 transition-colors"
            >
              <Users className="w-8 h-8 text-blue-500" />
              <span className="text-sm font-medium">NPC 管理</span>
            </a>
            <a
              href="/admin/scenes"
              className="flex flex-col items-center gap-2 p-4 rounded-lg border hover:bg-gray-50 transition-colors"
            >
              <Map className="w-8 h-8 text-green-500" />
              <span className="text-sm font-medium">场景管理</span>
            </a>
            <a
              href="/admin/quests"
              className="flex flex-col items-center gap-2 p-4 rounded-lg border hover:bg-gray-50 transition-colors"
            >
              <Target className="w-8 h-8 text-purple-500" />
              <span className="text-sm font-medium">任务管理</span>
            </a>
            <a
              href="/admin/releases"
              className="flex flex-col items-center gap-2 p-4 rounded-lg border hover:bg-gray-50 transition-colors"
            >
              <Activity className="w-8 h-8 text-orange-500" />
              <span className="text-sm font-medium">版本发布</span>
            </a>
          </div>
        </div>

        {/* System Status */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">系统状态</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-2 border-b">
              <span className="text-gray-600">API 服务</span>
              <span className="flex items-center gap-2 text-green-600">
                <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                正常
              </span>
            </div>
            <div className="flex items-center justify-between py-2 border-b">
              <span className="text-gray-600">数据库</span>
              <span className="flex items-center gap-2 text-green-600">
                <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                正常
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600">AI 服务</span>
              <span className="flex items-center gap-2 text-green-600">
                <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                正常
              </span>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
