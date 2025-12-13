'use client';

import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { StatsCard } from '@/components/dashboard/stats-card';
import { Users, MapPin, MessageSquare, Trophy } from 'lucide-react';

export default function DashboardPage() {
  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">仪表盘</h1>
          <p className="mt-1 text-sm text-gray-500">
            严田 AI 文明引擎运营数据概览
          </p>
        </div>

        {/* 统计卡片 */}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <StatsCard
            title="今日访客"
            value="128"
            change="+12%"
            changeType="increase"
            icon={Users}
          />
          <StatsCard
            title="活跃场景"
            value="12"
            change="0"
            changeType="neutral"
            icon={MapPin}
          />
          <StatsCard
            title="对话次数"
            value="456"
            change="+23%"
            changeType="increase"
            icon={MessageSquare}
          />
          <StatsCard
            title="完成任务"
            value="89"
            change="+8%"
            changeType="increase"
            icon={Trophy}
          />
        </div>

        {/* 快捷操作 */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">快捷操作</h2>
            <div className="mt-4 grid grid-cols-2 gap-4">
              <a
                href="/npcs"
                className="flex items-center rounded-lg border p-4 hover:bg-gray-50"
              >
                <MessageSquare className="h-8 w-8 text-primary-600" />
                <div className="ml-4">
                  <p className="font-medium text-gray-900">NPC 管理</p>
                  <p className="text-sm text-gray-500">编辑 NPC 人设</p>
                </div>
              </a>
              <a
                href="/quests"
                className="flex items-center rounded-lg border p-4 hover:bg-gray-50"
              >
                <Trophy className="h-8 w-8 text-primary-600" />
                <div className="ml-4">
                  <p className="font-medium text-gray-900">任务管理</p>
                  <p className="text-sm text-gray-500">配置研学任务</p>
                </div>
              </a>
              <a
                href="/scenes"
                className="flex items-center rounded-lg border p-4 hover:bg-gray-50"
              >
                <MapPin className="h-8 w-8 text-primary-600" />
                <div className="ml-4">
                  <p className="font-medium text-gray-900">场景管理</p>
                  <p className="text-sm text-gray-500">管理场景和 POI</p>
                </div>
              </a>
              <a
                href="/visitors"
                className="flex items-center rounded-lg border p-4 hover:bg-gray-50"
              >
                <Users className="h-8 w-8 text-primary-600" />
                <div className="ml-4">
                  <p className="font-medium text-gray-900">访客数据</p>
                  <p className="text-sm text-gray-500">查看访客画像</p>
                </div>
              </a>
            </div>
          </div>

          <div className="rounded-lg border bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-gray-900">最近活动</h2>
            <div className="mt-4 space-y-4">
              <div className="flex items-start">
                <div className="flex-shrink-0">
                  <div className="h-8 w-8 rounded-full bg-green-100 flex items-center justify-center">
                    <MessageSquare className="h-4 w-4 text-green-600" />
                  </div>
                </div>
                <div className="ml-3">
                  <p className="text-sm text-gray-900">
                    游客与「严氏先祖」完成对话
                  </p>
                  <p className="text-xs text-gray-500">2 分钟前</p>
                </div>
              </div>
              <div className="flex items-start">
                <div className="flex-shrink-0">
                  <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center">
                    <Trophy className="h-4 w-4 text-blue-600" />
                  </div>
                </div>
                <div className="ml-3">
                  <p className="text-sm text-gray-900">
                    游客完成「初识严田」任务
                  </p>
                  <p className="text-xs text-gray-500">15 分钟前</p>
                </div>
              </div>
              <div className="flex items-start">
                <div className="flex-shrink-0">
                  <div className="h-8 w-8 rounded-full bg-purple-100 flex items-center justify-center">
                    <Users className="h-4 w-4 text-purple-600" />
                  </div>
                </div>
                <div className="ml-3">
                  <p className="text-sm text-gray-900">新访客注册</p>
                  <p className="text-xs text-gray-500">30 分钟前</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
