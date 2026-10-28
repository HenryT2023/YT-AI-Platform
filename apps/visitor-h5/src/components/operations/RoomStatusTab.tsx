'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { CalendarDays, FileSpreadsheet, RefreshCw } from 'lucide-react'
import { Action, Empty, Notice, Panel, Pill, dateTime, inputClass } from './ui'

interface RoomObservation {
  observation_key: string
  date: string
  year: number
  month: number
  day: number
  room_type: string
  reported_type_capacity: number
  source_reported_reservation_quantity: number | null
  observed_status: string
  source_color: string | null
  source_sheet: string
  source_cell: string
  source_day_cell: string
  source_capacity_cell: string
  source_legend_cell: string | null
  source_year: number | null
  date_resolution: string
}
interface RoomStatusSource {
  filename: string
  sha256?: string
  sheet: string
  range: string
  business_as_of: string | null
  extracted_on?: string
  provenance?: string
}
interface RoomStatusSummary {
  room_type_day_cells: number
  blank_unknown_cells: number
  explicit_zero_cells: number
  positive_cells: number
  missing_coverage_days?: number
}
interface PeriodResolution {
  source_year: number | null
  resolved_year: number
  state: string
  basis: string
}
interface SnapshotMeta {
  id: string
  version: number
  parent_snapshot_id?: string | null
  imported_at: string
  source: RoomStatusSource
  period_resolution: PeriodResolution
  summary: RoomStatusSummary
  active?: boolean
}
interface RoomStatusSnapshot extends SnapshotMeta {
  room_capacity: {
    source_reported_total: number
    source_reported_twin: number
    source_reported_king: number
    owner_previously_reported_total: number
    unreconciled_difference: number
    source_ranges: string[]
    current_sellable_total: null
  }
  coverage: Array<{ year: number; month: number; from_day: number; through_day: number; days: number }>
  missing_coverage: Array<{ start_date: string; end_date: string; days: number }>
  observations: RoomObservation[]
  issues: Array<{ code: string; severity: string; message: string; count?: number; source_cells?: string[] }>
  opportunities: Array<{
    id: string
    start_date: string
    end_date: string
    room_types: string[]
    kind: 'ALL_TYPES_ZERO' | 'KING_ZERO'
    days: number
    verification_required: boolean
    source_cells: string[]
  }>
}
export interface RoomStatusData { active_snapshot: RoomStatusSnapshot | null; snapshots: SnapshotMeta[] }
export interface RoomStatusState { data: RoomStatusData | null; loading: boolean; error: string; reload: () => Promise<void> }

export function useRoomStatus(enabled: boolean): RoomStatusState {
  const [data, setData] = useState<RoomStatusData | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState('')
  const reload = useCallback(async () => {
    if (!enabled) return
    setLoading(true); setError('')
    try {
      const response = await fetch('/api/local-os/room-status', { cache: 'no-store' })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        throw new Error(typeof body.detail === 'string' ? body.detail : `最新房态暂时无法读取（${response.status}）`)
      }
      setData(await response.json())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '最新房态读取未完成，请重试。')
    } finally { setLoading(false) }
  }, [enabled])
  useEffect(() => { if (enabled) void reload() }, [enabled, reload])
  return { data, loading, error, reload }
}

function readableRange(start: string, end: string) { return start === end ? start : `${start} — ${end}` }
function recordedDates(snapshot: RoomStatusSnapshot) { return Array.from(new Set(snapshot.observations.map(item => item.date))).sort() }
function blankDates(snapshot: RoomStatusSnapshot) { return new Set(snapshot.observations.filter(item => item.observed_status === 'UNKNOWN_BLANK').map(item => item.date)).size }

export function RoomStatusOverview({ state, open, openLabel = '查看最新房态 →' }: { state: RoomStatusState; open: () => void; openLabel?: string }) {
  const snapshot = state.data?.active_snapshot
  return <section className="min-w-0 rounded-2xl border border-emerald-200 bg-[#f8faf3] p-5 sm:p-6">
    <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><div className="flex items-center gap-2"><FileSpreadsheet className="h-4 w-4 shrink-0 text-emerald-800" /><h2 className="text-sm font-semibold text-stone-800">最新房态 · 来源导入</h2></div>
      {snapshot ? <><p className="mt-2 break-words text-xs leading-6 text-stone-600">{snapshot.source.filename} · {snapshot.source.sheet} / {snapshot.source.range}</p><p className="mt-1 text-[11px] leading-6 text-stone-400">{snapshot.period_resolution.resolved_year} 年由用户补充 · 导入 v{snapshot.version} · {dateTime(snapshot.imported_at)}</p></> : <p className="mt-2 text-xs leading-6 text-stone-500">{state.loading ? '正在读取最新房态导入状态…' : state.error ? '导入状态读取未完成，不能判断为没有房态资料。' : '暂无房态导入快照；导入后保留源表和待核状态，不自动生成房号或订单。'}</p>}
    </div><Action onClick={open}>{openLabel}</Action></div>
    {snapshot && <div className="mt-3 flex flex-wrap gap-2"><Pill tone="amber">源记录待核对 · 非已核可售库存</Pill><Pill>{snapshot.observations.length} 条观察 / {recordedDates(snapshot).length} 个日期</Pill><Pill tone="amber">源表 {snapshot.room_capacity.source_reported_total} 间 / 此前声明 {snapshot.room_capacity.owner_previously_reported_total} 间 · 差 {snapshot.room_capacity.unreconciled_difference} 间</Pill><Pill tone="amber">{blankDates(snapshot)} 个日期含空白未知</Pill></div>}
    {state.error && <div role="alert" className="mt-3 flex flex-wrap items-center gap-3 text-xs leading-6 text-amber-900"><span>{state.error}</span><Action disabled={state.loading} onClick={() => void state.reload()}>重新读取</Action></div>}
  </section>
}

const statusLabels: Record<string, string> = {
  UNKNOWN_BLANK: '空白 · 未知',
  SOURCE_RECORDED_ZERO: '源表填 0',
  SOURCE_RESERVATION_UNCONFIRMED: '预订 · 未确认',
  SOURCE_RESERVATION_STATUS_UNRESOLVED: '预订标注 · 状态未核',
}
function ObservationCell({ item }: { item?: RoomObservation }) {
  if (!item) return <div className="rounded-lg border border-dashed border-stone-200 p-3 text-xs text-stone-400">未见此日期观察</div>
  const unknown = item.observed_status === 'UNKNOWN_BLANK'
  const zero = item.observed_status === 'SOURCE_RECORDED_ZERO'
  const pink = item.source_color === 'pink'
  const yellow = item.source_color === 'yellow'
  const style = unknown ? 'border-stone-200 bg-stone-100/80 text-stone-600' : pink ? 'border-rose-200 bg-rose-50 text-rose-900' : yellow ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-stone-200 bg-white text-stone-700'
  return <div className={`min-w-0 rounded-lg border px-3 py-2.5 ${style}`}>
    <div className="flex items-baseline justify-between gap-3"><strong className="text-base font-semibold">{item.source_reported_reservation_quantity == null ? '—' : item.source_reported_reservation_quantity}</strong><span className="text-[10px]">{statusLabels[item.observed_status] || '源状态待核'}</span></div>
    <p className="mt-1 text-[10px] leading-5 opacity-80">{unknown ? '未填写，不按 0 或空房处理' : zero ? '预订记录为 0，非可售量确认' : pink ? '粉色原标注，业务状态待核' : '黄色原标注，尚未确认'}</p>
    <div className="mt-1 flex flex-wrap gap-x-2 text-[10px] opacity-60"><span>{item.source_sheet}!{item.source_cell}</span><span>日期格 {item.source_day_cell}</span>{item.source_legend_cell && <span>图例 {item.source_legend_cell}</span>}</div>
  </div>
}

function SnapshotSource({ snapshot }: { snapshot: RoomStatusSnapshot }) {
  return <Panel title="来源与年份依据" note="保留表格原值、颜色标注与单元格定位；未把来源预订标注转换为订单或已确认房晚。"><dl className="grid gap-x-7 gap-y-4 text-xs leading-6 sm:grid-cols-2"><div className="min-w-0"><dt className="text-stone-400">来源文件</dt><dd className="break-words font-medium">{snapshot.source.filename}</dd></div><div><dt className="text-stone-400">工作表 / 读取范围</dt><dd>{snapshot.source.sheet} · {snapshot.source.range}</dd></div><div><dt className="text-stone-400">年份</dt><dd>{snapshot.period_resolution.resolved_year} 年 · 用户补充确认{snapshot.period_resolution.source_year == null ? '；源表未写年份' : ''}</dd></div><div><dt className="text-stone-400">业务截至时间</dt><dd>{snapshot.source.business_as_of || '源文件未提供，仍待核对'}</dd></div><div><dt className="text-stone-400">当前快照</dt><dd>v{snapshot.version} · {dateTime(snapshot.imported_at)} 导入</dd></div><div><dt className="text-stone-400">容量来源定位</dt><dd>{snapshot.room_capacity.source_ranges.map(value => `${snapshot.source.sheet}!${value}`).join('；')}</dd></div></dl><details className="mt-5 border-t border-stone-100 pt-4 text-xs text-stone-500"><summary className="cursor-pointer">查看可追溯信息</summary><div className="mt-3 space-y-2 break-all text-[11px] leading-6"><p>快照编号：{snapshot.id}</p><p>来源文件指纹：{snapshot.source.sha256 || '未提供'}</p><p>抽取日期：{snapshot.source.extracted_on || '未记录'}</p><p>年份依据：{snapshot.period_resolution.basis}</p></div></details></Panel>
}

export default function RoomStatusTab({ state }: { state: RoomStatusState }) {
  const [monthFilter, setMonthFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const snapshot = state.data?.active_snapshot
  if (!snapshot) return <div className="space-y-5"><RoomStatusOverview state={state} open={() => void state.reload()} openLabel="重新读取导入状态" /><Empty>{state.loading ? '正在读取最新房态…' : state.error ? '房态服务暂时不可用，请重新读取。读取失败不表示记录为空。' : '尚无已导入的房态快照。此模块只展示有来源的导入记录，不会补造房号、订单或可售量。'}</Empty></div>
  const dates = recordedDates(snapshot)
  const months = Array.from(new Set(dates.map(date => date.slice(0, 7))))
  const roomTypes = Array.from(new Set(snapshot.observations.map(item => item.room_type))).sort((a, b) => a === '双床' ? -1 : b === '双床' ? 1 : a.localeCompare(b, 'zh-CN'))
  const byDate = new Map<string, Map<string, RoomObservation>>()
  for (const item of snapshot.observations) { if (!byDate.has(item.date)) byDate.set(item.date, new Map()); byDate.get(item.date)!.set(item.room_type, item) }
  const visibleDates = dates.filter(date => (!monthFilter || date.startsWith(monthFilter)) && (!statusFilter || Array.from(byDate.get(date)?.values() || []).some(item => item.observed_status === statusFilter)))
  const bothTypeWindows = snapshot.opportunities.filter(item => item.kind === 'ALL_TYPES_ZERO')
  const kingWindows = snapshot.opportunities.filter(item => item.kind === 'KING_ZERO')
  const opportunityGroups = [
    { label: '双床与大床均填 0 的窗口', items: bothTypeWindows },
    { label: '大床填 0 的连续窗口', items: kingWindows },
  ]
  return <div className="min-w-0 space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-serif text-xl font-semibold">最新房态核对</h2><p className="mt-1 text-xs leading-6 text-stone-500">先看原记录，再按日期生成推广方案；确认方案后进入视频脚本。</p></div><Action disabled={state.loading} onClick={() => void state.reload()}><span className="inline-flex items-center gap-1"><RefreshCw className={`h-3 w-3 ${state.loading ? 'animate-spin' : ''}`} />{state.loading ? '读取中…' : '重新读取'}</span></Action></div>
    {state.error && <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-6 text-amber-900">{state.error} 当前仍展示此前成功读取的快照，请重试。</div>}
    <Notice><strong>源表预订记录，不是已核可售库存。</strong> 0 表示源表该格填了 0；空白保持未知。粉色预订业务状态待核，黄色预订尚未确认。没有逐房映射、完整渠道库存、报价与收款依据，不能据此生成已确认订单、入住率或收入。</Notice>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[
      ['日期与观察', `${dates.length} 个日期`, `${snapshot.observations.length} 条房型日观察 · ${snapshot.period_resolution.resolved_year} 年`],
      ['容量待核对', `差 ${snapshot.room_capacity.unreconciled_difference} 间`, `源表 ${snapshot.room_capacity.source_reported_total} 间 / 此前声明 ${snapshot.room_capacity.owner_previously_reported_total} 间`],
      ['空白保持未知', `${blankDates(snapshot)} 个日期`, `${snapshot.summary.blank_unknown_cells} 个空白格，不按 0 或空房补齐`],
      ['报价与收款', '缺少依据', '未形成报价 / 收款明细，不做营业收入确认'],
    ].map(([title, value, note]) => <div key={title} className="min-w-0 rounded-xl border border-stone-200 bg-white p-5"><p className="text-xs text-stone-400">{title}</p><p className="mt-3 font-serif text-2xl">{value}</p><p className="mt-2 text-[10px] leading-5 text-stone-500">{note}</p></div>)}</div>
    <Panel title="覆盖日期与未覆盖范围" note="未覆盖日期没有观察记录；不会自动补成零预订或可售房。"><div className="flex flex-wrap gap-2">{snapshot.coverage.map(item => <Pill key={`${item.year}-${item.month}`}>{item.year} 年 {item.month} 月 {item.from_day}–{item.through_day} 日 · {item.days} 天</Pill>)}</div>{snapshot.missing_coverage.length > 0 && <div className="mt-4 rounded-lg bg-amber-50 p-3 text-xs leading-6 text-amber-900"><strong>源表未覆盖：</strong>{snapshot.missing_coverage.map(item => `${readableRange(item.start_date, item.end_date)}（${item.days} 天）`).join('；')}。</div>}</Panel>
    <Panel title="可用于获客策划的待核日期" note="这些窗口仅来自源表的明确零记录；获客资料保留‘需核对房态’标记，不承诺可售间数。">
      {!snapshot.opportunities.length ? <Empty>当前快照没有可列出的零记录窗口，不补造空房机会。</Empty> : <div className="space-y-5">{opportunityGroups.map(({ items, label }) => <div key={label}><h3 className="mb-3 text-xs font-medium text-stone-600">{label}</h3><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{items.map(opportunity => <article key={opportunity.id} className="min-w-0 rounded-xl border border-emerald-100 bg-emerald-50/40 p-4"><div className="flex flex-wrap gap-2"><Pill tone="amber">房态待核实</Pill><Pill>{opportunity.room_types.join(' / ')}</Pill></div><h4 className="mt-3 text-sm font-semibold">{readableRange(opportunity.start_date, opportunity.end_date)}</h4><p className="mt-1 text-[11px] text-stone-500">共 {opportunity.days} 天 · 含末日</p><p className="mt-3 text-xs leading-6 text-stone-500">{opportunity.kind === 'ALL_TYPES_ZERO' ? '这两类房型的源表预订格均为 0。' : '大床房源表预订格连续为 0；不代表双床状态相同。'}先核对其他渠道、维修、自用与新订单，再形成对外承诺。</p><details className="mt-3 text-[10px] text-stone-400"><summary className="cursor-pointer">原件单元格 · {opportunity.source_cells.length} 格</summary><p className="mt-2 break-words leading-6">{opportunity.source_cells.join('、')}</p></details><Link href={`/workspace?room_snapshot=${encodeURIComponent(snapshot.id)}&room_window=${encodeURIComponent(opportunity.id)}`} className="mt-4 inline-flex items-center gap-1 rounded-lg bg-emerald-800 px-3 py-2.5 text-xs font-medium text-white hover:bg-emerald-900"><CalendarDays className="h-3.5 w-3.5" />按此日期生成运营方案 →</Link></article>)}</div></div>)}</div>}
    </Panel>
    <Panel title="逐日房态原记录" note="数值是源表填写的预订房间数量，不是订单数或已确认入住。筛选只筛日期，仍同时保留各房型原记录。">
      <div className="mb-4 flex flex-wrap gap-3"><label className="min-w-[150px] flex-1 text-xs text-stone-500"><span className="mb-1.5 block">月份</span><select value={monthFilter} onChange={event => setMonthFilter(event.target.value)} className={inputClass}><option value="">全部覆盖月份</option>{months.map(month => <option key={month} value={month}>{month.replace('-', ' 年 ')} 月</option>)}</select></label><label className="min-w-[180px] flex-1 text-xs text-stone-500"><span className="mb-1.5 block">筛选包含此标记的日期</span><select value={statusFilter} onChange={event => setStatusFilter(event.target.value)} className={inputClass}><option value="">全部标记</option>{Object.entries(statusLabels).map(([status, label]) => <option key={status} value={status}>{label}</option>)}</select></label></div>
      <div className="mb-4 flex flex-wrap gap-x-4 gap-y-2 text-[10px] text-stone-500"><span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded border border-stone-300 bg-stone-100" />灰：空白未知</span><span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded border border-amber-300 bg-amber-50" />黄：预订未确认</span><span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded border border-rose-300 bg-rose-50" />粉：业务状态未核</span><span>0：源表明确填 0，非已核可售</span></div>
      <p className="mb-3 text-[11px] text-stone-400">显示 {visibleDates.length} / {dates.length} 个有记录日期；表格可局部横向、纵向滚动。</p>
      <div className="max-h-[620px] max-w-full overflow-auto rounded-xl border border-stone-200" role="region" aria-label="逐日双床与大床源记录" tabIndex={0}><table className="w-full min-w-[620px] border-collapse text-left text-xs"><caption className="sr-only">源表房型日观察，0 与空白含义分开，包含原件单元格；不展示推算可售房。</caption><thead className="sticky top-0 z-10 bg-stone-50 shadow-sm"><tr><th scope="col" className="w-[120px] px-4 py-3 font-medium text-stone-500">日期</th>{roomTypes.map(roomType => <th key={roomType} scope="col" className="px-3 py-3 font-medium text-stone-500">{roomType}<span className="ml-2 text-[10px] font-normal text-stone-400">源表容量 {snapshot.observations.find(item => item.room_type === roomType)?.reported_type_capacity ?? '未知'} 间</span></th>)}</tr></thead><tbody className="divide-y divide-stone-100">{visibleDates.map(date => <tr key={date} className="bg-white align-top"><th scope="row" className="whitespace-nowrap px-4 py-4 font-medium text-stone-600">{date}</th>{roomTypes.map(roomType => <td key={roomType} className="min-w-[240px] px-3 py-2"><ObservationCell item={byDate.get(date)?.get(roomType)} /></td>)}</tr>)}</tbody></table></div>
      {!visibleDates.length && <div className="mt-4"><Empty>当前筛选没有对应日期，可切换月份或标记。</Empty></div>}
    </Panel>
    <div className="grid min-w-0 gap-5 lg:grid-cols-2"><Panel title="核对问题与缺口" note="以下问题保持打开，不通过填 0、生成房号或模拟交易消除。">{!snapshot.issues.length ? <p className="text-xs leading-6 text-stone-500">快照未附问题清单；仍需按来源边界核验。</p> : <div className="space-y-3">{snapshot.issues.map((issue, index) => <div key={`${issue.code}-${index}`} className="min-w-0 rounded-xl border border-amber-100 bg-amber-50/60 p-3"><p className="text-xs leading-6 text-amber-900">{issue.message}</p>{issue.source_cells?.length ? <p className="mt-1 break-words text-[10px] leading-5 text-amber-700">出处：{issue.source_cells.join('、')}</p> : null}</div>)}</div>}</Panel><SnapshotSource snapshot={snapshot} /></div>
    <Panel title="导入历史" note="保留来源版本；当前列表只提供历史元数据，不把旧快照混入当前观察。"><div className="divide-y divide-stone-100">{(state.data?.snapshots || []).map(item => <div key={item.id} className="flex min-w-0 flex-wrap items-start justify-between gap-3 py-3"><div className="min-w-0"><p className="break-words text-xs font-medium">{item.source.filename}</p><p className="mt-1 text-[10px] leading-5 text-stone-400">导入 v{item.version} · {dateTime(item.imported_at)} · {item.source.sheet} / {item.source.range}</p></div><Pill tone={item.id === snapshot.id ? 'green' : 'neutral'}>{item.id === snapshot.id ? '当前快照' : '历史元数据'}</Pill></div>)}</div></Panel>
  </div>
}
