'use client'

import Link from 'next/link'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowUpRight, BedDouble, CalendarDays, ClipboardList, Download, LayoutDashboard, Megaphone, Package, RefreshCw, X } from 'lucide-react'
import { LOCAL_OS_MODE } from '@/lib/config'
import { Mutate, Snapshot, TabProps, channelName, orderStates } from '@/components/operations/types'
import { API_BASE, Action, Empty, Notice, Panel, Pill, dateTime, money, readAPI } from '@/components/operations/ui'
import { ProductsTab, RoomsTab } from '@/components/operations/CatalogTabs'
import MarketingTab from '@/components/operations/MarketingTab'
import OrdersTab from '@/components/operations/OrdersTab'
import RoomStatusTab, { RoomStatusOverview, useRoomStatus, type RoomStatusState } from '@/components/operations/RoomStatusTab'

const tabs = [
  { id: 'overview', title: '经营概览', icon: LayoutDashboard },
  { id: 'room-status', title: '最新房态', icon: CalendarDays },
  { id: 'rooms', title: '房源房态', icon: BedDouble },
  { id: 'products', title: '住宿与体验', icon: Package },
  { id: 'channels', title: '渠道与内容', icon: Megaphone },
  { id: 'orders', title: '订单台账', icon: ClipboardList },
] as const
type Tab = typeof tabs[number]['id']

function Overview({ data, navigate, roomStatus }: { data: Snapshot; navigate: (tab: Tab) => void; roomStatus: RoomStatusState }) {
  const summary = data.summary
  const statistics = [
    { label: '已建档客房', value: `${summary.rooms_registered} 间`, note: `声明容量 ${data.settings.room_capacity} 间 · 未建档 ${summary.unregistered_rooms} 间` },
    { label: '当前有效订单', value: `${summary.active_orders} 笔`, note: `暂留 ${summary.hold_orders} · 已确认 ${summary.confirmed_orders}` },
    { label: '已登记收款', value: summary.received_cents == null ? '未登记' : money(summary.received_cents), note: '人工流水登记 · 无银行或支付核验' },
    { label: '已登记净收款', value: summary.net_received_cents == null ? '未登记' : money(summary.net_received_cents), note: `已登记退款：${summary.refunded_cents == null ? '未登记' : money(summary.refunded_cents)}` },
  ]
  const currentOrders = [...data.orders].reverse().slice(0, 5)
  return <div className="space-y-5">
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{statistics.map(stat => <div key={stat.label} className="rounded-2xl border border-stone-200 bg-white p-5"><p className="text-xs text-stone-500">{stat.label}</p><p className="mt-3 break-words font-serif text-2xl text-stone-800">{stat.value}</p><p className="mt-2 text-[10px] leading-5 text-stone-400">{stat.note}</p></div>)}</div>
    <RoomStatusOverview state={roomStatus} open={() => navigate('room-status')} />
    <Notice><strong>基线与实绩分开。</strong> {data.settings.season}住宿参考 {money(data.settings.reference_price_cents)}/晚，逐单报价另行确认；声明容量不等于可售房量。当前营业收入尚未确认，不能以参考价、订单报价或收款记录代替营业收入。</Notice>
    <p className="px-1 text-[11px] text-stone-400">基线来源：{typeof data.settings.provenance === 'string' ? data.settings.provenance : '来源状态待核对'}。</p>
    <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
      <Panel title="把真实经营连成一条线" note="从可交付产品与库存开始，留下每一步的实际记录。"><div className="space-y-3">{[
        { title: '1 · 核对实际客房', description: `${data.rooms.length} 间已建档；按日期查询可售房，维修封房单独记录。`, target: 'rooms' as Tab, button: '管理房态' },
        { title: '2 · 确认住宿与体验', description: `${data.products.length} 项产品、${data.sessions.length} 个场次。未知交付能力先保留草稿。`, target: 'products' as Tab, button: '管理产品' },
        { title: '3 · 留下渠道与咨询', description: `${data.leads.length} 条咨询、${data.content_drafts.length} 份内部草稿。以来源码保留归因。`, target: 'channels' as Tab, button: '跟进咨询' },
        { title: '4 · 登记订单到履约', description: `${data.orders.length} 笔订单。报价、暂留、人工收退款与履约分别记录。`, target: 'orders' as Tab, button: '进入台账' },
      ].map(step => <div key={step.title} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-stone-50 px-4 py-3"><div><h3 className="text-sm font-medium">{step.title}</h3><p className="mt-1 text-xs leading-6 text-stone-500">{step.description}</p></div><Action onClick={() => navigate(step.target)}>{step.button} →</Action></div>)}</div></Panel>
      <Panel title="本地记录状态" note="本页没有连接外部平台、支付网关或设备。"><div className="space-y-4 text-xs leading-6"><div className="flex justify-between gap-3"><span className="text-stone-500">营业收入确认</span><Pill tone="amber">尚未建立确认口径</Pill></div><div className="flex justify-between gap-3"><span className="text-stone-500">订单人工报价合计</span><span>{data.orders.length ? money(summary.quoted_total_cents) : '未登记订单'}</span></div><div className="flex justify-between gap-3"><span className="text-stone-500">收款 / 退款记录</span><span>{summary.payments_count} / {summary.refunds_count} 条</span></div><div className="flex justify-between gap-3"><span className="text-stone-500">实际履约登记</span><span>{summary.fulfilled_orders} 笔</span></div><div className="border-t border-stone-100 pt-3 text-stone-400">{summary.note || '手工登记仅表示本地台账已记录，不能替代外部到账、现场交付或财务审核。'}</div></div><div className="mt-5 flex flex-wrap gap-3 text-xs text-emerald-800"><a href="/studio/#knowledge" className="underline">文化知识</a><a href="/studio/#designs" className="underline">木刻稿样</a><a href="/stay" className="underline">预览独立站</a></div></Panel>
    </div>
    <Panel title="最近订单" note="全部来自本地实际登记，不预填客户、订单或资金流水。" action={<Action onClick={() => navigate('orders')}>全部订单 →</Action>}>{!currentOrders.length ? <Empty>尚无订单记录。<br />先登记实际产品与库存，再按真实咨询创建订单。</Empty> : <div className="divide-y divide-stone-100">{currentOrders.map(order => <div key={order.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div><p className="text-sm font-medium">{order.label}</p><p className="mt-1 text-xs text-stone-400">{channelName(order.channel_id)} · {dateTime(order.created_at)}</p></div><div className="flex items-center gap-3"><Pill tone={order.status === 'confirmed' || order.status === 'fulfilled' ? 'green' : 'neutral'}>{orderStates[order.status]}</Pill><span className="text-sm font-medium">{money(order.amount_cents)}</span></div></div>)}</div>}</Panel>
  </div>
}

export default function OperationsPage() {
  const [data, setData] = useState<Snapshot | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const lock = useRef(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loadedAt, setLoadedAt] = useState('')
  const roomStatus = useRoomStatus(LOCAL_OS_MODE)
  const refresh = useCallback(async () => {
    const snapshot = await readAPI<Snapshot>('')
    setData(snapshot); setLoadedAt(new Date().toISOString())
  }, [])
  useEffect(() => {
    if (!LOCAL_OS_MODE) { setLoading(false); return }
    let mounted = true
    refresh().catch(cause => { if (mounted) setError(cause instanceof Error ? cause.message : '本地经营台账暂不可用') }).finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [refresh])
  useEffect(() => { const readHash = () => { const id = window.location.hash.slice(1); if (tabs.some(item => item.id === id)) setTab(id as Tab) }; readHash(); window.addEventListener('hashchange', readHash); return () => window.removeEventListener('hashchange', readHash) }, [])
  function navigate(next: Tab) { setTab(next); window.history.replaceState(null, '', `#${next}`) }
  const mutate: Mutate = async (path, payload = {}, method = 'POST') => {
    if (lock.current) return false
    lock.current = true; setBusy(true); setError(''); setMessage('')
    try {
      const response = await fetch(`${API_BASE}${path}`, { method, headers: { 'Content-Type': 'application/json', 'X-Yantian-Local': '1' }, body: JSON.stringify(payload) })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) {
        const detail = typeof result.detail === 'string' ? result.detail : Array.isArray(result.detail) ? result.detail.map((item: { msg?: string }) => item.msg || '输入格式不正确').join('；') : `保存未完成（${response.status}）`
        throw new Error(detail)
      }
      await refresh(); setMessage('本地记录已保存，台账已更新。'); return true
    } catch (cause) { setError(cause instanceof Error ? cause.message : '操作未完成，输入已保留，请稍后重试。'); return false }
    finally { lock.current = false; setBusy(false) }
  }
  const props: TabProps | null = data ? { data, mutate, busy } : null
  return <div className="min-h-screen bg-[#f5f4ee] text-stone-800">
    <header className="border-b border-stone-200 bg-white/90"><div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-7"><div className="flex items-center gap-4"><Link href="/" className="flex items-center gap-1 text-xs text-stone-500 hover:text-emerald-800"><ArrowLeft className="h-4 w-4" />返回严田 OS</Link><span className="hidden h-5 border-l border-stone-200 sm:block" /><span className="text-xs font-medium tracking-wider text-emerald-900">严田 · 运营工作台</span></div><div className="flex items-center gap-2"><Link href="/growth" className="rounded-lg border border-emerald-200 px-3 py-2 text-xs text-emerald-900">内容与获客</Link><Link href="/stay" className="flex items-center gap-1 rounded-lg border border-stone-200 px-3 py-2 text-xs">预览独立站<ArrowUpRight className="h-3 w-3" /></Link><a href={`${API_BASE}/export`} download className="flex items-center gap-1 rounded-lg bg-emerald-800 px-3 py-2 text-xs text-white"><Download className="h-3 w-3" />导出台账</a></div></div></header>
    <main className="mx-auto max-w-7xl px-4 py-6 sm:px-7 sm:py-8">
      <div className="mb-6 flex items-start justify-between gap-4"><div><p className="mb-2 text-[10px] uppercase tracking-[.2em] text-stone-400">LOCAL OPERATIONS</p><h1 className="font-serif text-2xl font-semibold sm:text-3xl">{data?.settings.property_name || '严田经营工作台'}</h1><p className="mt-2 text-xs leading-6 text-stone-500">房态、交付、咨询与订单，按实际记录推进。当前为本地人工台账，不连接在线收款或外部营销平台。</p></div><button disabled={loading || busy} onClick={async () => { setLoading(true); setError(''); try { await Promise.all([refresh(), roomStatus.reload()]) } catch (cause) { setError(cause instanceof Error ? cause.message : '刷新未完成') } finally { setLoading(false) } }} aria-label="刷新经营台账" className="rounded-full border border-stone-200 bg-white p-3 text-stone-500 disabled:opacity-40"><RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /></button></div>
      <div className="mb-5 flex flex-wrap items-center gap-2"><Pill tone="green">本地手工台账</Pill><Pill>未确认营业收入</Pill><Pill>机器未启用</Pill>{loadedAt && <span className="text-[10px] text-stone-400">读取于 {dateTime(loadedAt)}</span>}</div>
      <nav aria-label="经营模块" className="mb-6 flex gap-1 overflow-x-auto rounded-xl border border-stone-200 bg-white p-1.5">{tabs.map(item => <button key={item.id} onClick={() => navigate(item.id)} aria-current={tab === item.id ? 'page' : undefined} className={`flex min-w-max flex-1 items-center justify-center gap-2 rounded-lg px-4 py-3 text-xs font-medium ${tab === item.id ? 'bg-emerald-800 text-white' : 'text-stone-500 hover:bg-stone-50'}`}><item.icon className="h-4 w-4" />{item.title}</button>)}</nav>
      {error && <div role="alert" className="mb-5 flex items-start justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs leading-6 text-red-800"><span>{error} 表单输入已保留。</span><button onClick={() => setError('')} aria-label="关闭错误提示"><X className="mt-1 h-4 w-4" /></button></div>}
      {message && <div role="status" className="mb-5 flex justify-between gap-3 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-xs text-emerald-800"><span>{message}</span><button onClick={() => setMessage('')} aria-label="关闭保存提示"><X className="h-4 w-4" /></button></div>}
      {!LOCAL_OS_MODE ? <Empty>运营工作台仅在明确启用的本地 OS 模式开放。请从本地统一入口进入。</Empty> : tab === 'room-status' ? <RoomStatusTab state={roomStatus} /> : !props ? <Empty>{loading ? '正在读取本地经营资料…' : '尚未取得经营台账。请刷新重试，不以空白视为经营数据为零。'}</Empty> : tab === 'overview' ? <Overview data={props.data} navigate={navigate} roomStatus={roomStatus} /> : tab === 'rooms' ? <RoomsTab {...props} /> : tab === 'products' ? <ProductsTab {...props} /> : tab === 'channels' ? <MarketingTab {...props} /> : <OrdersTab {...props} />}
      <footer className="mt-8 border-t border-stone-200 pt-5 text-[10px] leading-6 text-stone-400">严田 OS · 经营事实与文化创作共用入口，分别保留证据。记录、报价、收款、履约和收入确认彼此独立。</footer>
    </main>
  </div>
}
