'use client'
import Link from 'next/link'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, ClipboardCheck, FolderOpen, Layers3, Megaphone, RefreshCw, TrendingUp, X } from 'lucide-react'
import { LOCAL_OS_MODE } from '@/lib/config'
import { CampaignsTab, AssetsTab } from '@/components/growth/CampaignAssets'
import PackageWorkbench from '@/components/growth/PackageWorkbench'
import RoomWindowBridge from '@/components/growth/RoomWindowBridge'
import { ReviewTab, ResultsTab } from '@/components/growth/ReviewResults'
import { Context, GrowthSnapshot, Save } from '@/components/growth/types'
import { Empty, GROWTH_API, Notice, Pill, dateTime, isApproved } from '@/components/growth/ui'

const tabs = [
  { id: 'campaigns', title: '获客任务', icon: Megaphone },
  { id: 'assets', title: '拍摄素材', icon: FolderOpen },
  { id: 'video', title: '脚本与成片', icon: Layers3 },
  { id: 'review', title: '审阅与导出', icon: ClipboardCheck },
  { id: 'results', title: '线索复盘', icon: TrendingUp },
] as const
const visibleTabs = [tabs[2], tabs[1], tabs[3]]

export default function GrowthPage() {
  const [data, setData] = useState<GrowthSnapshot | null>(null)
  const [campaignId, setCampaignId] = useState('')
  const [packageId, setPackageId] = useState('')
  const [tab, setTab] = useState('video')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loadedAt, setLoadedAt] = useState('')
  const lock = useRef(false)
  const refresh = useCallback(async () => {
    const response = await fetch(GROWTH_API, { cache: 'no-store' })
    if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(typeof body.detail === 'string' ? body.detail : `本地获客资料暂不可用（${response.status}）`) }
    setData(await response.json()); setLoadedAt(new Date().toISOString())
  }, [])
  useEffect(() => { if (!LOCAL_OS_MODE) { setLoading(false); return }; refresh().catch(cause => setError(cause instanceof Error ? cause.message : '本地服务暂不可用')).finally(() => setLoading(false)) }, [refresh])
  useEffect(() => { const readHash = () => { const next = location.hash.slice(1); if (tabs.some(item => item.id === next)) setTab(next) }; readHash(); addEventListener('hashchange', readHash); return () => removeEventListener('hashchange', readHash) }, [])
  useEffect(() => {
    if (!data) return
    const query = new URLSearchParams(location.search)
    const requested = data.campaigns.find(item => item.id === query.get('campaign')) || data.campaigns.find(item => item.workspace_plan_ref?.plan_id === query.get('workspace_plan')) || data.campaigns.find(item => item.room_status_ref?.snapshot_id === query.get('room_snapshot') && item.room_status_ref?.opportunity_id === query.get('room_window'))
    const id = data.campaigns.some(item => item.id === campaignId) ? campaignId : requested?.id || data.campaigns[0]?.id || ''
    if (id !== campaignId) setCampaignId(id)
    if (!data.packages.some(pkg => pkg.id === packageId && pkg.campaign_id === id)) { const related = data.packages.filter(pkg => pkg.campaign_id === id); setPackageId(related[related.length - 1]?.id || '') }
  }, [data, campaignId, packageId])
  function navigate(next: string) { setTab(next); history.replaceState(null, '', `${location.pathname}${location.search}#${next}`) }
  function choose(id: string) { setCampaignId(id); const related = data?.packages.filter(pkg => pkg.campaign_id === id) || []; setPackageId(related[related.length - 1]?.id || '') }
  const save: Save = async <T,>(path: string, payload: unknown, method: 'POST' | 'PUT' = 'POST'): Promise<T | null> => {
    if (lock.current) return null
    lock.current = true; setBusy(true); setError(''); setMessage('')
    try {
      const multipart = payload instanceof FormData
      const response = await fetch(`${GROWTH_API}${path}`, { method, headers: { 'X-Yantian-Local': '1', ...(multipart ? {} : { 'Content-Type': 'application/json' }) }, body: multipart ? payload : JSON.stringify(payload) })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : Array.isArray(result.detail) ? result.detail.map((item: { msg?: string }) => item.msg || '输入格式不正确').join('；') : `保存未完成（${response.status}）`)
      await refresh(); setMessage('本地记录已保存。资料、审阅和分发声明分别留痕，未自动发布。'); return result as T
    } catch (cause) { setError(cause instanceof Error ? cause.message : '本地操作未完成，输入已保留。'); return null }
    finally { lock.current = false; setBusy(false) }
  }
  const campaign = data?.campaigns.find(item => item.id === campaignId) || null
  const context: Context | null = data ? { data, campaign, save, busy, navigate, packageId, selectPackage: setPackageId } : null
  const currentPackage = data?.packages.find(pkg => pkg.id === packageId)
  const approved = currentPackage && data ? (currentPackage.approval_valid ?? isApproved(currentPackage.id, currentPackage.hash, data.reviews)) : false
  return <div className="min-h-screen bg-[#f5f4ee] text-stone-800"><header className="border-b border-stone-200 bg-white"><div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-7"><div className="flex items-center gap-4"><Link href="/workspace" className="flex items-center gap-1 text-xs text-stone-500"><ArrowLeft className="h-4 w-4" />返回运营方案</Link><span className="text-xs font-medium tracking-wider text-emerald-900">严田 · 第二层 / 脚本与成片</span></div><div className="flex gap-3 text-xs text-emerald-800"><Link href="/operations" className="rounded-lg border border-stone-200 px-3 py-2">咨询与订单台账 ↗</Link><Link href={campaign ? `/stay?source=${encodeURIComponent(campaign.source_code)}` : '/stay'} className="rounded-lg border border-stone-200 px-3 py-2">预览咨询承接页 ↗</Link></div></div></header>
    <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-7 sm:py-8"><div className="mb-5 flex items-start justify-between gap-4"><div><p className="mb-2 text-[10px] tracking-[.2em] text-stone-400">YANTIAN / 02</p><h1 className="font-serif text-2xl font-semibold sm:text-3xl">从确认的方案，做到本地视频</h1><p className="mt-2 max-w-3xl text-xs leading-6 text-stone-500">先在第一层确认推广方案，再编排脚本、分镜与素材。保存并确认脚本后，手动生成视频，在这里预览和下载。</p></div><button aria-label="刷新获客资料" disabled={busy || loading} onClick={async () => { setLoading(true); setError(''); try { await refresh() } catch (cause) { setError(cause instanceof Error ? cause.message : '刷新未完成') } finally { setLoading(false) } }} className="rounded-full border border-stone-200 bg-white p-3 disabled:opacity-40"><RefreshCw className={`h-4 w-4 text-stone-500 ${loading ? 'animate-spin' : ''}`} /></button></div>
      <div className="mb-5 flex flex-wrap gap-2"><Pill tone="green">本地确定性资料编排</Pill><Pill>无大模型连接</Pill><Pill>本地生成视频 / 不自动发布</Pill>{loadedAt && <span className="py-1 text-[10px] text-stone-400">读取于 {dateTime(loadedAt)}</span>}</div>
      <div className="mb-5 flex flex-wrap gap-3 text-[11px] text-stone-400"><a href="/workspace" className="text-emerald-800 underline">① 运营方案</a><span>→</span><strong className="font-medium text-emerald-900">② 脚本与成片</strong><span>→</span><span>③ 乡村管理模型 · 后续独立建设</span></div>
      {campaign?.workspace_plan_ref ? <div className="mb-5"><Notice><strong>来自已确认的第一层方案。</strong> 本页处理视频脚本、分镜与本地成片，方案中的房态、文化项目和报价待核项继续保留。<a href={`/workspace?plan=${encodeURIComponent(campaign.workspace_plan_ref.plan_id)}`} className="ml-2 text-emerald-900 underline">查看运营方案 →</a></Notice></div> : <div className="mb-5"><Notice>这里保留既有视频任务。新工作从第一层开始：<a href="/workspace" className="text-emerald-900 underline">输入需求，生成并确认运营方案 →</a></Notice></div>}
      {data && <RoomWindowBridge campaigns={data.campaigns} save={save} busy={busy} choose={choose} navigate={navigate} />}
      <div className="mb-5 rounded-xl border border-stone-200 bg-white p-4"><div className="grid min-w-0 grid-cols-1 items-center gap-3 lg:grid-cols-[minmax(220px,1fr)_2fr]"><label className="flex min-w-0 items-center gap-3 text-xs text-stone-500"><span className="shrink-0">当前脚本任务</span><select value={campaignId} onChange={event => choose(event.target.value)} className="min-w-0 flex-1 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-800"><option value="">{data?.campaigns.length ? '请选择任务' : '尚未建立任务'}</option>{data?.campaigns.map(item => <option key={item.id} value={item.id}>{item.title} · v{item.version}</option>)}</select></label><div className="flex flex-wrap items-center gap-2 text-[11px] text-stone-400"><span className={campaign ? 'text-emerald-800' : ''}>① 编排脚本</span><span>→</span><span className={currentPackage ? 'text-emerald-800' : ''}>② 保存分镜</span><span>→</span><span>③ 确认并生成本地视频</span><span>→</span><span className={approved ? 'text-emerald-800' : ''}>④ 独立发布审阅</span></div></div>{campaign && <p className="mt-3 border-t border-stone-100 pt-3 text-[11px] text-stone-500">来源码 <strong className="font-medium text-emerald-900">{campaign.source_code}</strong> · 目标：{campaign.objective}{campaign.room_status_ref && <> · <a href="/operations#room-status" className="text-emerald-800 underline">已绑定房态来源与日期窗口</a></>}</p>}</div>
      <nav aria-label="内容与获客模块" className="mb-6 flex gap-1 overflow-x-auto rounded-xl border border-stone-200 bg-white p-1.5">{visibleTabs.map(item => <button key={item.id} aria-current={tab === item.id ? 'page' : undefined} onClick={() => navigate(item.id)} className={`flex min-w-max flex-1 items-center justify-center gap-2 rounded-lg px-4 py-3 text-xs font-medium ${tab === item.id ? 'bg-emerald-800 text-white' : 'text-stone-500 hover:bg-stone-50'}`}><item.icon className="h-4 w-4" />{item.title}</button>)}</nav>
      <details className="mb-5 text-xs text-stone-500"><summary className="cursor-pointer">历史任务与经营复盘</summary><div className="mt-3 flex flex-wrap gap-3"><button onClick={() => navigate('campaigns')} className="rounded-lg border border-stone-200 bg-white px-3 py-2">既有任务记录</button><button onClick={() => navigate('results')} className="rounded-lg border border-stone-200 bg-white px-3 py-2">渠道与线索复盘</button><a href="/operations" className="rounded-lg border border-stone-200 bg-white px-3 py-2">房态与订单台账</a></div></details>
      {error && <div role="alert" className="sticky top-3 z-20 mb-5 flex justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs leading-6 text-red-800 shadow-sm"><span>{error} 当前输入已保留。</span><button aria-label="关闭错误" onClick={() => setError('')}><X className="mt-1 h-4 w-4" /></button></div>}{message && <div role="status" className="mb-5 flex justify-between gap-3 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-xs leading-6 text-emerald-800"><span>{message}</span><button aria-label="关闭提示" onClick={() => setMessage('')}><X className="mt-1 h-4 w-4" /></button></div>}
      {!LOCAL_OS_MODE ? <Empty>内容与获客仅在明确启用的本地 OS 模式开放。</Empty> : !context ? <Empty>{loading ? '正在读取获客任务与素材…' : '尚未取得本地资料，请刷新重试；不把读取失败视为记录为零。'}</Empty> : tab === 'campaigns' ? <CampaignsTab {...context} choose={choose} /> : tab === 'assets' ? <AssetsTab {...context} /> : tab === 'video' ? <PackageWorkbench {...context} /> : tab === 'review' ? <ReviewTab {...context} /> : <ResultsTab {...context} />}
      <footer className="mt-8 border-t border-stone-200 pt-5 text-[10px] leading-6 text-stone-400">严田 OS · 内容、材料、审阅与人工分发分别留痕。咨询与订单从原运营台账按来源码回流；已登记净收款不等于营业收入或利润。</footer>
    </main></div>
}
