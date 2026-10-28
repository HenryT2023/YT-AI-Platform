'use client'

import { useEffect, useState } from 'react'
import { BookOpen, FileQuestion, PenTool, ClipboardCheck, RefreshCw, ArrowUpRight, Megaphone } from 'lucide-react'

interface LocalOSStatus {
  mode?: string
  model?: { connected?: boolean; mode?: string }
  machines?: { enabled?: boolean }
  machine?: { enabled?: boolean }
  studio?: { counts?: Record<string, number> }
  counts?: Record<string, number>
  knowledge?: { canonical?: boolean; shared?: boolean; count?: number }
  canonical_knowledge?: boolean | Record<string, unknown>
}

const entries = [
  { href: '/growth', title: '内容与获客', note: '选题、视频资料与线索复盘', icon: Megaphone },
  { href: '/operations', title: '运营工作台', note: '房态、产品与订单台账', icon: ClipboardCheck },
  { href: '/studio/#knowledge', title: '文化知识', note: '来源、范围与版本', icon: BookOpen },
  { href: '/studio/#qa', title: '文化问答', note: '原文出处、争议与缺口', icon: FileQuestion },
  { href: '/studio/#designs', title: '木刻稿样', note: '原创设计与可编辑SVG', icon: PenTool },
  { href: '/studio/#reviews', title: '审阅反馈', note: '精确版本，待审候选', icon: ClipboardCheck },
]

export default function LocalOSPanel({ compact = false }: { compact?: boolean }) {
  const [status, setStatus] = useState<LocalOSStatus | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  async function refresh() {
    setLoading(true); setError('')
    try {
      const response = await fetch('/api/local-os/status', { cache: 'no-store' })
      if (!response.ok) throw new Error(`本地整合状态未读取（${response.status}）`)
      setStatus(await response.json())
    } catch (cause) { setStatus(null); setError(cause instanceof Error ? cause.message : '本地服务暂不可用') }
    finally { setLoading(false) }
  }
  useEffect(() => { refresh() }, [])
  const machine = status?.machines || status?.machine
  const counts = status?.studio?.counts || status?.counts
  const canonical = status?.canonical_knowledge
  const sharedKnowledge = canonical && typeof canonical === 'object'
    && canonical.storage === 'single_sqlite'
    && Array.isArray(canonical.shared_with)
    && canonical.shared_with.includes('studio') && canonical.shared_with.includes('npc')
  return (
    <section className="rounded-2xl border border-emerald-200 bg-[#f8faf3] p-4 text-slate-800 shadow-sm dark:border-slate-700 dark:bg-slate-800">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] tracking-widest text-emerald-700 dark:text-emerald-400">严田 OS · 内容获客与住宿承接</p>
          <h2 className="mt-1 font-semibold">从内容获客，到住宿咨询与文化体验</h2>
          <p className="mt-2 text-xs leading-6 text-slate-500 dark:text-slate-400">住宿获客为主线，文化与木刻提供内容支线。视频资料、审阅分发、咨询订单按来源码接续；文化工作室共用一份知识库，原 NPC、研学任务和状态入口继续保留。</p>
        </div>
        <button onClick={refresh} disabled={loading} aria-label="刷新本地整合状态" className="rounded-full p-2 text-slate-500 hover:bg-emerald-50 disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /></button>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-[11px]" aria-live="polite">
        <span className={`rounded px-2 py-1 ${status ? 'bg-emerald-100 text-emerald-800' : error ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-500'}`}>{loading ? '正在读取整合状态' : status ? '本地整合接口已连接' : error}</span>
        {status && <span className="rounded bg-white px-2 py-1 text-slate-600 dark:bg-slate-700 dark:text-slate-300">{status.model?.connected === false ? '无生成式模型 · 本地证据检索' : '模型状态见系统页'}</span>}
        {sharedKnowledge && <span className="rounded bg-white px-2 py-1 text-emerald-800 dark:bg-slate-700 dark:text-emerald-300">NPC / 工作室 · 同一知识库</span>}
        {machine?.enabled === false && <span className="rounded bg-white px-2 py-1 text-slate-600 dark:bg-slate-700 dark:text-slate-300">机器预留 · 未启用</span>}
        {typeof counts?.knowledge === 'number' && <span className="rounded bg-white px-2 py-1 text-slate-600 dark:bg-slate-700 dark:text-slate-300">{counts.knowledge} 条当前知识</span>}
      </div>
      {!compact && <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
        {entries.map(({ href, title, note, icon: Icon }) => <a key={href} href={href} className="group rounded-xl border border-slate-200 bg-white p-3 transition hover:border-emerald-400 hover:bg-emerald-50 dark:border-slate-600 dark:bg-slate-900">
          <div className="flex items-center justify-between text-emerald-700"><Icon className="h-5 w-5" /><ArrowUpRight className="h-3 w-3 opacity-50" /></div><h3 className="mt-3 text-sm font-medium">{title}</h3><p className="mt-1 text-[10px] leading-5 text-slate-500">{note}</p>
        </a>)}
      </div>}
      <p className="mt-3 text-[10px] leading-5 text-slate-500">专属权重尚未训练；反馈只形成待审候选。页面连接不等于设备、现场制作或经营履约已完成。</p>
    </section>
  )
}
