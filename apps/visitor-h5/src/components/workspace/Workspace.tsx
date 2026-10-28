'use client'

import Link from 'next/link'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowUpRight, Check, ChevronDown, HelpCircle, Clock3, FileStack, Leaf, Loader2, LockKeyhole, Plus, RefreshCw, X } from 'lucide-react'
import Composer from './Composer'
import PlanResult from './PlanResult'
import { AttachmentDTO, PlanDTO, RoomReference, SelectedAttachment, WorkspaceSnapshot, dateLabel, evidenceLabel, postJSON, roomDateLabel, workspaceRequest } from './types'
import { Tag, secondaryButton } from './ui'

const auxiliaryLinks = [
  { href: '/operations#room-status', title: '最新房态' },
  { href: '/operations#products', title: '住宿与体验目录' },
  { href: '/growth', title: '既有内容资料' },
  { href: '/studio/#qa', title: '有出处的文化问答' },
  { href: '/studio/#knowledge', title: '文化资料与来源' },
  { href: '/studio/#designs', title: '木刻稿样' },
  { href: '/operations#orders', title: '订单台账' },
  { href: '/stay', title: '住宿咨询预览' },
  { href: '/?view=visitor', title: '原游客与任务入口' },
  { href: '/health', title: '本地服务状态' },
]

function selectedFrom(attachment: AttachmentDTO): SelectedAttachment { return { key: attachment.id, name: attachment.name, state: attachment.integrity_state === 'missing_or_changed' ? 'failed' : 'ready', attachment, error: attachment.integrity_state === 'missing_or_changed' ? '本地材料已缺失或变化，请重新添加或移除。' : undefined } }
function attachmentsForPlan(plan: PlanDTO, attachments: AttachmentDTO[]): SelectedAttachment[] {
  return plan.request.attachment_ids.map(id => {
    const attachment = attachments.find(item => item.id === id)
    return attachment ? selectedFrom(attachment) : { key: id, name: '历史附加材料（暂不可用）', state: 'failed', error: '本地材料未找到，请重新添加或从本次任务移除。' }
  })
}
function openedPlanNotice(plan: PlanDTO) { return plan.superseded ? '已打开历史版本。可以查看，或以此内容另建新方案；不能再次确认旧版。' : '已打开这版方案；修改输入后可生成新版本。' }
function updatePlanUrl(id: string) {
  const query = new URLSearchParams(window.location.search)
  query.set('plan', id); query.delete('room_snapshot'); query.delete('room_window')
  window.history.replaceState(null, '', `${window.location.pathname}?${query.toString()}`)
}
function sameAttachments(left: string[], right: string[]) { const sortedRight = right.slice().sort(); return left.length === right.length && left.slice().sort().every((value, index) => value === sortedRight[index]) }
function sameRoomReference(left?: RoomReference | null, right?: RoomReference | null) { return (left?.snapshot_id || '') === (right?.snapshot_id || '') && (left?.opportunity_id || '') === (right?.opportunity_id || '') }
const extensions = /\.(jpe?g|png|webp|txt|md|csv|xlsx|docx|pdf)$/i

export default function Workspace() {
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [brief, setBrief] = useState('')
  const [selected, setSelected] = useState<SelectedAttachment[]>([])
  const [result, setResult] = useState<PlanDTO | null>(null)
  const [roomRef, setRoomRef] = useState<RoomReference | null>(null)
  const [action, setAction] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const queryApplied = useRef(false)
  const lock = useRef(false)
  const previews = useRef(new Set<string>())
  const composerRef = useRef<HTMLDivElement>(null)
  const busy = Boolean(action)
  const roomStatus = snapshot?.reference_summary.room_status
  const roomSnapshotId = roomStatus?.id || roomStatus?.snapshot_id
  const roomWindow = roomRef && roomRef.snapshot_id === roomSnapshotId ? roomStatus?.opportunities?.find(window => window.id === roomRef.opportunity_id) : undefined
  const sourceUnavailable = Boolean(roomRef && snapshot && !roomWindow)
  const selectedIds = Array.from(new Set(selected.flatMap(item => item.state === 'ready' && item.attachment ? [item.attachment.id] : [])))
  const dirty = Boolean(result && (brief.trim() !== result.request.brief.trim() || !sameAttachments(selectedIds, result.request.attachment_ids) || !sameRoomReference(roomRef, result.room_status_ref) || selected.some(item => item.state !== 'ready')))
  const canGenerate = Boolean(snapshot && (brief.trim() || selectedIds.length) && !selected.some(item => item.state !== 'ready') && !sourceUnavailable)

  const refresh = useCallback(async () => {
    setLoading(true)
    try { const data = await workspaceRequest<WorkspaceSnapshot>(''); setSnapshot(data); return data }
    finally { setLoading(false) }
  }, [])
  useEffect(() => {
    let mounted = true
    const query = new URLSearchParams(window.location.search)
    const snapshotId = query.get('room_snapshot'), opportunityId = query.get('room_window')
    if (snapshotId && opportunityId) setRoomRef({ snapshot_id: snapshotId, opportunity_id: opportunityId })
    workspaceRequest<WorkspaceSnapshot>('').then(data => {
      if (!mounted) return
      setSnapshot(data)
    }).catch(cause => { if (mounted) setError(cause instanceof Error ? cause.message : '参考资料暂未读取，请重试。') }).finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [])
  useEffect(() => {
    if (queryApplied.current || !snapshot) return
    queryApplied.current = true
    const requestedPlan = new URLSearchParams(window.location.search).get('plan')
    if (requestedPlan) {
      const plan = snapshot.plans.find(item => item.id === requestedPlan)
      if (!plan) { setError('未找到链接中的运营方案。请从历史方案选择现有版本，或新建方案；当前未自动确认任何内容。'); return }
      setResult(plan); setBrief(plan.request.brief)
      setSelected(attachmentsForPlan(plan, snapshot.attachments)); setRoomRef(plan.room_status_ref || null)
      setNotice(openedPlanNotice(plan))
      requestAnimationFrame(() => document.getElementById('workspace-plan')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
      return
    }
    if (roomWindow) setBrief(current => current || `推广 ${roomDateLabel(roomWindow)} 的住宿，搭配严田 CREATE 文化体验。房态以核对结果为准。`)
  }, [snapshot, roomWindow])
  useEffect(() => () => { previews.current.forEach(url => URL.revokeObjectURL(url)) }, [])

  async function retryRead() {
    setError('')
    try { await refresh() } catch (cause) { setError(cause instanceof Error ? cause.message : '读取未完成，请重试。') }
  }
  async function upload(key: string, file: File) {
    setSelected(current => current.map(item => item.key === key ? { ...item, state: 'uploading', error: undefined } : item))
    try {
      const body = new FormData(); body.append('file', file)
      const attachment = await workspaceRequest<AttachmentDTO>('/attachments', { method: 'POST', body })
      setSelected(current => current.map(item => item.key === key ? { ...item, state: 'ready', attachment } : item))
      setSnapshot(current => current ? { ...current, attachments: [attachment, ...current.attachments.filter(item => item.id !== attachment.id)] } : current)
    } catch (cause) {
      setSelected(current => current.map(item => item.key === key ? { ...item, state: 'failed', error: cause instanceof Error ? cause.message : '材料上传未完成' } : item))
    }
  }
  function addFiles(files: FileList | null) {
    if (!files || busy) return
    const remaining = Math.max(0, 12 - selected.length)
    if (files.length > remaining) setError('每次方案最多选择 12 份材料；超出的材料尚未添加。')
    const pending: SelectedAttachment[] = []
    for (const file of Array.from(files).slice(0, remaining)) {
      const key = crypto.randomUUID()
      const invalid = file.size > 10 * 1024 * 1024 ? '超过单份 10 MiB，请缩小后再添加。' : !extensions.test(file.name) ? '暂不支持此格式，请换用支持的照片或文档。' : ''
      const local_preview = !invalid && /^image\/(jpeg|png|webp)$/.test(file.type) ? URL.createObjectURL(file) : undefined
      if (local_preview) previews.current.add(local_preview)
      pending.push({ key, name: file.name, file: invalid ? undefined : file, local_preview, state: invalid ? 'failed' : 'uploading', error: invalid || undefined })
    }
    setSelected(current => [...current, ...pending])
    for (const item of pending) { if (item.file) void upload(item.key, item.file) }
  }
  function removeAttachment(key: string) {
    const item = selected.find(entry => entry.key === key)
    if (item?.local_preview) { URL.revokeObjectURL(item.local_preview); previews.current.delete(item.local_preview) }
    setSelected(current => current.filter(entry => entry.key !== key))
  }
  function selectAttachment(attachment: AttachmentDTO) {
    if (selected.length >= 12) { setError('每次方案最多选择 12 份材料。'); return }
    setSelected(current => current.some(item => item.attachment?.id === attachment.id) ? current : [...current, selectedFrom(attachment)])
  }
  function replacePlan(plan: PlanDTO) {
    setResult(plan)
    setSnapshot(current => current ? { ...current, plans: [plan, ...current.plans.filter(item => item.id !== plan.id)] } : current)
  }
  function focusComposer() {
    composerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    document.getElementById('workspace-brief')?.focus({ preventScroll: true })
  }
  function choosePlan(plan: PlanDTO) {
    previews.current.forEach(url => URL.revokeObjectURL(url)); previews.current.clear()
    setResult(plan); setBrief(plan.request.brief)
    setSelected(attachmentsForPlan(plan, snapshot?.attachments || []))
    setRoomRef(plan.room_status_ref || null)
    setError(''); setNotice(openedPlanNotice(plan)); updatePlanUrl(plan.id)
    requestAnimationFrame(() => document.getElementById('workspace-plan')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }
  function newPlan() {
    if (busy) return
    previews.current.forEach(url => URL.revokeObjectURL(url)); previews.current.clear()
    setResult(null); setBrief(''); setSelected([]); setRoomRef(null); setError(''); setNotice('')
    window.history.replaceState(null, '', window.location.pathname)
    focusComposer()
  }
  async function generate() {
    if (lock.current || !canGenerate) return
    lock.current = true; setAction('generate'); setError(''); setNotice('')
    try {
      const plan = await postJSON<PlanDTO>('/plans', { brief: brief.trim(), attachment_ids: selectedIds, ...(roomRef ? { room_status_ref: roomRef } : {}), ...(result && !result.superseded ? { base_plan_id: result.id } : {}) })
      replacePlan(plan)
      setBrief(plan.request.brief)
      setRoomRef(plan.room_status_ref || null)
      updatePlanUrl(plan.id)
      setNotice(plan.request.brief !== brief.trim() ? '运营方案已整理，输入已按本地资料边界处理。先核对方向与待核项，再决定是否确认。' : '运营方案已整理。先核对方向与待核项，再决定是否确认。')
      requestAnimationFrame(() => document.getElementById('workspace-plan')?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
    } catch (cause) { setError(cause instanceof Error ? cause.message : '方案未能生成，输入与材料已保留。') }
    finally { lock.current = false; setAction('') }
  }
  async function confirm() {
    if (!result || busy || dirty || result.source_stale || result.superseded || result.blockers?.length || lock.current) return
    lock.current = true; setAction('confirm'); setError(''); setNotice('')
    try { replacePlan(await postJSON<PlanDTO>(`/plans/${encodeURIComponent(result.id)}/confirm`, { plan_hash: result.hash })); setNotice('此版策划方向已确认。你可以选择进入第二层，待核事项仍保留。') }
    catch (cause) {
      setError(cause instanceof Error ? cause.message : '确认未完成，请重试。')
      try { const current = await refresh(); setResult(previous => previous ? current.plans.find(plan => plan.id === previous.id) || previous : previous) } catch { /* Keep the confirmation error and current inputs visible. */ }
    }
    finally { lock.current = false; setAction('') }
  }
  async function handoff() {
    if (!result || !result.confirmation_valid || result.source_stale || dirty || lock.current) return
    lock.current = true; setAction('handoff'); setError(''); setNotice('')
    try {
      const next = await postJSON<{ campaign_id: string; url: string }>(`/plans/${encodeURIComponent(result.id)}/video-handoffs`, { plan_hash: result.hash })
      const url = new URL(next.url, window.location.origin)
      if (url.origin !== window.location.origin || !url.pathname.startsWith('/growth')) throw new Error('脚本工作区地址异常，请重新读取后再试。')
      window.location.assign(url.href)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '交接未完成，请重试。'); lock.current = false; setAction('') }
  }

  return <div className="min-h-screen bg-[#f5f4ee] text-stone-800">
    <header className="border-b border-stone-200/80 bg-white/80"><div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-8"><Link href="/" className="flex items-center gap-3"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-950 text-white"><Leaf className="h-4 w-4" /></span><div><span className="text-sm font-semibold tracking-widest">严田</span><span className="ml-3 text-[11px] text-stone-400">运营工作空间</span></div></Link><button type="button" disabled={busy} onClick={newPlan} className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs text-stone-500 hover:bg-stone-100 disabled:opacity-40"><Plus className="h-3.5 w-3.5" />新建方案</button></div></header>
    <main className="mx-auto max-w-5xl px-5 pb-10 pt-7 sm:px-8 sm:pt-10">
      <nav aria-label="工作流程" className="mb-8 grid grid-cols-3 gap-2 border-b border-stone-200/80 pb-5 text-[10px] sm:gap-5 sm:text-xs"><div aria-current="step" className="flex items-start gap-2 font-medium text-emerald-950"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-950 text-[10px] text-white">1</span><span className="pt-0.5">运营方案</span></div><div className={`flex items-start gap-2 ${result?.confirmation_valid && !result.source_stale && !dirty ? 'text-emerald-800' : 'text-stone-400'}`}><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-stone-300 text-[10px]">2</span><span className="pt-0.5">视频脚本<span className="mt-1 block text-[9px] font-normal sm:text-[10px]">方案确认后进入</span></span></div><div className="flex items-start gap-2 text-stone-400"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-stone-300 text-[10px]">3</span><span className="pt-0.5">乡村管理模型<span className="mt-1 block text-[9px] font-normal sm:text-[10px]">后续独立建设</span></span></div></nav>
      <div className="mb-6"><p className="mb-2 text-[10px] tracking-[.18em] text-emerald-800/70">第一层 · 想清楚，再行动</p><h1 className="font-serif text-2xl font-semibold leading-relaxed sm:text-3xl">把一句话，整理成严田的运营方案</h1><p className="mt-3 max-w-2xl text-xs leading-7 text-stone-500 sm:text-sm">围绕住房推广与 CREATE 文化体验，说出你的想法，附上手边的材料。先确定怎么经营，再把已确认的方案交给视频脚本。</p></div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap items-center gap-2"><span className="h-1.5 w-1.5 rounded-full bg-emerald-700" /><span className="text-[10px] text-stone-500">本地资料编排 · 未连接生成式模型</span>{loading && <Loader2 aria-label="正在读取参考资料" className="h-3 w-3 animate-spin text-stone-400" />}</div><details className="relative text-xs text-stone-500"><summary className="flex cursor-pointer list-none items-center gap-1.5"><Clock3 className="h-3.5 w-3.5" />历史方案{snapshot?.plans.length ? ` · ${snapshot.plans.length}` : ''}<ChevronDown className="h-3 w-3" /></summary><div className="absolute right-0 z-20 mt-3 max-h-80 w-[min(360px,calc(100vw-48px))] overflow-auto rounded-xl border border-stone-200 bg-white p-2 shadow-lg">{snapshot?.plans.length ? snapshot.plans.map(plan => <button key={plan.id} disabled={busy} onClick={event => { choosePlan(plan); event.currentTarget.closest('details')?.removeAttribute('open') }} className="block w-full rounded-lg p-3 text-left hover:bg-stone-50 disabled:opacity-40"><span className="block truncate text-xs font-medium">{plan.plan.title}</span><span className="mt-1 block text-[10px] leading-5 text-stone-400">v{plan.version} · {dateLabel(plan.created_at)} · {plan.superseded ? '历史旧版' : plan.source_stale ? '来源更新待重做' : plan.confirmation_valid ? '已确认方向' : '待确认'}</span></button>) : <p className="p-3 text-xs leading-6 text-stone-400">{loading ? '正在读取…' : !snapshot ? '历史方案尚未读取，请重试参考资料。' : '还没有保存的运营方案。'}</p>}</div></details></div>
      {error && <div role="alert" className="mb-4 flex items-start justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-6 text-amber-900"><div><p>{error}</p><p className="mt-1 text-[10px]">输入和本次选中的材料已保留。</p>{!snapshot && <button type="button" onClick={() => void retryRead()} disabled={loading} className="mt-2 inline-flex items-center gap-1 underline"><RefreshCw className="h-3 w-3" />重新读取参考资料</button>}</div><button type="button" aria-label="关闭提示" onClick={() => setError('')} className="shrink-0 rounded p-1"><X className="h-3.5 w-3.5" /></button></div>}
      {notice && <p role="status" className="mb-4 flex items-start gap-2 rounded-lg bg-emerald-50 px-4 py-3 text-xs leading-6 text-emerald-900"><Check className="mt-1 h-3.5 w-3.5 shrink-0" />{notice}</p>}
      <div ref={composerRef} className="scroll-mt-6"><Composer brief={brief} setBrief={setBrief} selected={selected} attachments={snapshot?.attachments || []} busy={busy} generating={action === 'generate'} canGenerate={canGenerate} editing={Boolean(result)} onFiles={addFiles} onRemove={removeAttachment} onRetry={key => { const item = selected.find(entry => entry.key === key); if (item?.file) void upload(key, item.file) }} onSelect={selectAttachment} onGenerate={() => void generate()} context={roomRef ? <div className={`mt-3 flex min-w-0 items-start justify-between gap-3 rounded-lg border p-3 text-xs leading-6 ${sourceUnavailable ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-emerald-100 bg-emerald-50/50 text-emerald-900'}`}><div className="min-w-0"><p className="font-medium">{roomWindow ? `房态日期：${roomDateLabel(roomWindow)}` : loading ? '正在核对关联的房态日期…' : '关联房态来源已变化或日期窗口不存在'}</p><p className="mt-1 text-[10px]">{roomWindow ? `源表${roomWindow.room_types?.join(' / ') || ''}填零的待核窗口，含末日；不代表已核可售库存。` : '请从最新房态重新选择，或移除此日期依据再生成。'}</p><Link href="/operations#room-status" className="mt-1 inline-block text-[10px] underline">查看原表与核对问题</Link></div><button type="button" disabled={busy} onClick={() => setRoomRef(null)} aria-label="移除本次房态日期依据" className="shrink-0 rounded p-1"><X className="h-3.5 w-3.5" /></button></div> : undefined} /></div>
      <details className="mt-5 rounded-xl border border-stone-200/80 bg-white/40 text-xs text-stone-500"><summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 px-4 py-3.5"><span className="inline-flex items-center gap-2"><FileStack className="h-3.5 w-3.5" />本次可参考的严田资料</span><span className="inline-flex items-center gap-2 text-[10px] text-stone-400">{snapshot ? `${snapshot.reference_summary.create_routes?.length || 0} 项 CREATE 目录 · ${roomStatus ? '有房态来源' : '暂无房态来源'}` : '资料状态待读取'}<ChevronDown className="h-3 w-3" /></span></summary><div className="space-y-5 border-t border-stone-200/70 p-4 sm:p-5"><p className="text-[11px] leading-6 text-stone-500">已整合的本机资料保留来源与原始状态。目录存在不等于当日可交付；方案价格不由参考住宿价推算。</p>{snapshot?.reference_summary.create_routes?.length ? <div><h2 className="mb-3 text-xs font-medium text-stone-700">CREATE 文化体验目录</h2><div className="grid gap-3 sm:grid-cols-2">{snapshot.reference_summary.create_routes.map(route => <div key={route.id} className="min-w-0 rounded-lg border border-stone-200 bg-white p-3"><p className="text-xs font-medium text-stone-700">{route.title}</p>{route.summary && <p className="mt-1 text-[11px] leading-6">{route.summary}</p>}<p className="mt-2 text-[10px] text-amber-800">{evidenceLabel(route.status)} · 实际交付条件待核</p></div>)}</div></div> : null}{roomStatus?.opportunities?.length ? <div><h2 className="mb-3 text-xs font-medium text-stone-700">源表待核日期窗口</h2><div className="flex flex-wrap gap-2">{roomStatus.opportunities.map(window => <button key={window.id} disabled={busy || !roomSnapshotId} onClick={() => { if (!roomSnapshotId) return; setRoomRef({ snapshot_id: roomSnapshotId, opportunity_id: window.id }); setBrief(current => current || `推广 ${roomDateLabel(window)} 的住宿，搭配严田 CREATE 文化体验。房态以核对结果为准。`) }} className={secondaryButton}>{roomDateLabel(window)}<span className="text-[10px] text-amber-700">待核</span></button>)}</div></div> : null}<Link href="/operations#room-status" className="inline-flex items-center gap-1 text-xs text-emerald-800 underline">查看完整房态来源<ArrowUpRight className="h-3 w-3" /></Link></div></details>
      {result ? <div className="mt-7"><PlanResult result={result} busy={busy} action={action} dirty={dirty} onConfirm={() => void confirm()} onHandoff={() => void handoff()} onEdit={focusComposer} /></div> : <div className="mt-7 flex items-start gap-3 px-1 text-stone-400"><HelpCircle className="mt-0.5 h-4 w-4 shrink-0" /><p className="text-[11px] leading-6">生成后会得到经营目标、住宿与体验组合、客群假设、渠道安排、具体动作和待核清单。这里先做方案，不会直接生成脚本或发布内容。</p></div>}
      <details className="mt-8 border-t border-stone-200 pt-5 text-xs text-stone-500"><summary className="flex cursor-pointer list-none items-center justify-between gap-3"><span>辅助资料与记录</span><ChevronDown className="h-3.5 w-3.5" /></summary><div className="mt-4 flex flex-wrap gap-x-5 gap-y-3">{auxiliaryLinks.map(link => <a key={link.href} href={link.href} className="inline-flex items-center gap-1 text-[11px] text-emerald-800 hover:underline">{link.title}<ArrowUpRight className="h-3 w-3" /></a>)}</div><p className="mt-4 flex gap-2 text-[10px] leading-5 text-stone-400"><LockKeyhole className="mt-0.5 h-3 w-3 shrink-0" />乡村管理模型作为后续独立层建设。当前未训练专属模型，未连接自动发布、在线收款或机器设备。</p></details>
    </main>
  </div>
}
