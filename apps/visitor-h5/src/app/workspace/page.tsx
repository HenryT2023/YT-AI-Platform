'use client'

import Link from 'next/link'
import Workspace from '@/components/workspace/Workspace'
import { LOCAL_OS_MODE } from '@/lib/config'

export default function WorkspacePage() {
  if (LOCAL_OS_MODE) return <Workspace />
  return <main className="mx-auto max-w-xl px-6 py-20 text-sm leading-7 text-stone-600"><h1 className="mb-3 text-xl font-semibold">严田运营工作空间</h1><p>此工作空间在明确启用的本地 OS 模式开放。</p><Link href="/" className="mt-5 inline-block text-emerald-800 underline">返回首页</Link></main>
}
