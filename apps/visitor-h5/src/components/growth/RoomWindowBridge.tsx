'use client'
import { useEffect, useState } from 'react'
import { Campaign, Save } from './types'
import { Action, Notice, Panel, Pill } from './ui'

interface WindowOpportunity { id: string; start_date: string; end_date: string; kind: string; days: number; room_types: string[]; source_cells: string[] }
interface RoomSnapshot { id: string; source: { filename: string; sha256: string }; opportunities: WindowOpportunity[]; summary: { blank_unknown_cells: number } }
export default function RoomWindowBridge({ campaigns, busy, choose, navigate }: { campaigns: Campaign[]; save: Save; busy: boolean; choose: (id: string) => void; navigate: (tab: string) => void }) {
  const [selection, setSelection] = useState<{ snapshot: string; window: string } | null>(null)
  const [snapshot, setSnapshot] = useState<RoomSnapshot | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const query = new URLSearchParams(location.search)
    const snapshot = query.get('room_snapshot'), window = query.get('room_window')
    if (snapshot && window) setSelection({ snapshot, window })
  }, [])
  useEffect(() => {
    if (!selection) return
    const controller = new AbortController()
    setLoading(true); setError('')
    fetch('/api/local-os/room-status', { cache: 'no-store', signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error('房态来源暂不可读，请重试')
      const data = await response.json()
      if (data.active_snapshot?.id !== selection.snapshot) throw new Error('房态来源版本已变化，请返回最新房态重新选择日期')
      if (!data.active_snapshot.opportunities.some((item: WindowOpportunity) => item.id === selection.window)) throw new Error('该日期窗口不在当前来源中，请重新选择')
      setSnapshot(data.active_snapshot)
    }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '房态来源读取失败') }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [selection, attempt])
  if (!selection) return null
  const opportunity = snapshot?.opportunities.find(item => item.id === selection.window)
  const campaign = campaigns.find(item => item.room_status_ref?.snapshot_id === selection.snapshot && item.room_status_ref?.opportunity_id === selection.window)
  return <div className="mb-5"><Panel title="从最新房态带入的获客日期" note="来源表的零预订日期用于选题；核房和体验交付确认后，再确定售卖安排。" action={<a href="/operations#room-status" className="shrink-0 whitespace-nowrap text-xs text-emerald-800 underline">返回最新房态</a>}>
    {loading ? <p className="text-xs text-stone-500">正在核对日期来源…</p> : error ? <div role="alert" className="text-xs leading-6 text-red-800">{error}<div className="mt-2"><Action onClick={() => setAttempt(value => value + 1)}>重新读取</Action></div></div> : opportunity && snapshot ? <>
      <div className="flex flex-wrap items-center gap-2"><strong className="text-sm">{opportunity.start_date} 至 {opportunity.end_date}</strong><Pill>{opportunity.room_types.join('、')} · 原表填0预订</Pill><Pill tone="amber">待核房与报价</Pill></div>
      <p className="mt-3 text-xs leading-6 text-stone-500">住宿＋文化体验为现成产品。具体体验、场次、价格和房型安排逐项核对，未确认的木刻包含项保留为策划参考。</p>
      <p className="mt-2 break-words text-[10px] leading-5 text-stone-400">出处：{snapshot.source.filename} · Sheet1 · {opportunity.source_cells.join('、')}。年份2026来自管理者补充；来源版本 {snapshot.id}。</p>
      <div className="mt-4 flex flex-wrap items-center gap-3"><a href={`/workspace?room_snapshot=${encodeURIComponent(snapshot.id)}&room_window=${encodeURIComponent(opportunity.id)}`} className="rounded-lg bg-emerald-800 px-3 py-2.5 text-xs font-medium text-white">先生成运营方案 →</a>{campaign && <Action disabled={busy} onClick={() => { choose(campaign.id); navigate('video') }}>查看既有视频资料</Action>}</div>
    </> : <Notice>尚未取得有效日期来源，请返回最新房态重试。</Notice>}
  </Panel></div>
}
