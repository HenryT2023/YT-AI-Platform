'use client';

import { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  Users,
  MapPin,
  MessageSquare,
  Trophy,
  Settings,
  Menu,
  X,
  LogOut,
} from 'lucide-react';
import { SiteSwitcher } from './site-switcher';
import clsx from 'clsx';

const navigation = [
  { name: '仪表盘', href: '/admin/dashboard', icon: LayoutDashboard },
  { name: 'NPC 管理', href: '/admin/npcs', icon: MessageSquare },
  { name: '场景管理', href: '/admin/scenes', icon: MapPin },
  { name: '任务管理', href: '/admin/quests', icon: Trophy },
  { name: '访客数据', href: '/admin/visitors', icon: Users },
  { name: '游客画像', href: '/admin/visitor-profiles', icon: Users },
  { name: '成就管理', href: '/admin/achievements', icon: Trophy },
  { name: '系统设置', href: '/admin/settings', icon: Settings },
];

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' });
    router.push('/login');
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Mobile sidebar */}
      <div
        className={clsx(
          'fixed inset-0 z-50 lg:hidden',
          sidebarOpen ? 'block' : 'hidden'
        )}
      >
        <div
          className="fixed inset-0 bg-gray-900/50"
          onClick={() => setSidebarOpen(false)}
        />
        <div className="fixed inset-y-0 left-0 w-64 bg-white shadow-xl">
          <div className="flex h-16 items-center justify-between px-4">
            <span className="text-lg font-bold text-primary-700">严田后台</span>
            <button onClick={() => setSidebarOpen(false)}>
              <X className="h-6 w-6 text-gray-500" />
            </button>
          </div>
          <nav className="mt-4 px-2">
            {navigation.map((item) => (
              <Link
                key={item.name}
                href={item.href}
                className={clsx(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium',
                  pathname.startsWith(item.href)
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-700 hover:bg-gray-100'
                )}
              >
                <item.icon className="h-5 w-5" />
                {item.name}
              </Link>
            ))}
          </nav>
        </div>
      </div>

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
        <div className="flex flex-1 flex-col border-r bg-white">
          <div className="flex h-16 items-center justify-between px-6">
            <span className="text-xl font-bold text-primary-700">
              严田 AI 引擎
            </span>
          </div>
          <div className="px-4 pb-2">
            <SiteSwitcher />
          </div>
          <nav className="flex-1 px-4 py-4">
            {navigation.map((item) => (
              <Link
                key={item.name}
                href={item.href}
                className={clsx(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium mb-1',
                  pathname.startsWith(item.href)
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-700 hover:bg-gray-100'
                )}
              >
                <item.icon className="h-5 w-5" />
                {item.name}
              </Link>
            ))}
          </nav>
          <div className="border-t p-4">
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
            >
              <LogOut className="h-5 w-5" />
              退出登录
            </button>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="lg:pl-64">
        {/* Top bar */}
        <div className="sticky top-0 z-40 flex h-16 items-center gap-4 border-b bg-white px-4 lg:px-8">
          <button
            className="lg:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-6 w-6 text-gray-500" />
          </button>
          <div className="flex-1" />
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-600">管理员</span>
            <div className="h-8 w-8 rounded-full bg-primary-100 flex items-center justify-center">
              <span className="text-sm font-medium text-primary-700">A</span>
            </div>
          </div>
        </div>

        {/* Page content */}
        <main className="p-4 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
