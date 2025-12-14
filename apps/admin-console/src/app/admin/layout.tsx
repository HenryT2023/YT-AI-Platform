'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  MessageSquare,
  FileJson,
  LayoutDashboard,
  ChevronRight,
  Package,
  Bell,
} from 'lucide-react';

const NAV_ITEMS = [
  {
    href: '/admin/releases',
    label: 'Release 管理',
    icon: Package,
    description: '灰度发布配置包管理',
  },
  {
    href: '/admin/alerts',
    label: '告警管理',
    icon: Bell,
    description: '监控告警事件与静默规则',
  },
  {
    href: '/admin/feedback',
    label: '反馈工单',
    icon: MessageSquare,
    description: '管理用户反馈，跟踪处理进度',
  },
  {
    href: '/admin/policies/evidence-gate',
    label: 'Evidence Gate 策略',
    icon: FileJson,
    description: '管理证据闸门策略配置',
  },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Top Navigation */}
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/" className="flex items-center gap-2">
                <LayoutDashboard className="w-6 h-6 text-blue-600" />
                <span className="font-bold text-gray-900">严田 AI 运营后台</span>
              </Link>
              <ChevronRight className="w-4 h-4 text-gray-400" />
              <span className="text-gray-600">Admin</span>
            </div>
          </div>
        </div>
      </nav>

      <div className="flex">
        {/* Sidebar */}
        <aside className="w-64 bg-white shadow-sm min-h-[calc(100vh-4rem)] border-r">
          <div className="p-4">
            <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">
              运营管理
            </h2>
            <nav className="space-y-1">
              {NAV_ITEMS.map((item) => {
                const isActive = pathname === item.href;
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                      isActive
                        ? 'bg-blue-50 text-blue-700 font-medium'
                        : 'text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    <Icon className={`w-5 h-5 ${isActive ? 'text-blue-600' : 'text-gray-400'}`} />
                    <div>
                      <div>{item.label}</div>
                      <div className="text-xs text-gray-500 font-normal">
                        {item.description}
                      </div>
                    </div>
                  </Link>
                );
              })}
            </nav>
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
