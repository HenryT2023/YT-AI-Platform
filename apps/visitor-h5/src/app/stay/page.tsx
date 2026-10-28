'use client'

import Link from 'next/link'
import { useEffect, useState, type FormEvent } from 'react'
import { ArrowLeft, ArrowUpRight, BedDouble, BookOpen, CalendarDays, CheckCircle2, Leaf } from 'lucide-react'

type Product = { id: string; title: string; kind: string; description: string; price_cents: number | null }
type Catalog = {
  settings: { property_name: string; room_capacity: number; reference_price_cents: number; season: string }
  products: Product[]
}
const money = (value: number) => (value / 100).toLocaleString('zh-CN', { maximumFractionDigits: 2 })

export default function StayPreview() {
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/local-os/operations/catalog', { cache: 'no-store', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error('商品资料暂时无法读取，请返回运营台检查。')
        setCatalog(await response.json())
      })
      .catch(cause => { if (cause.name !== 'AbortError') setError(cause.message) })
    return () => controller.abort()
  }, [])
  async function inquire(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setSuccess(''); setBusy(true)
    const form = event.currentTarget
    const fields = new FormData(form)
    const start = String(fields.get('start_date') || '')
    const end = String(fields.get('end_date') || '')
    if (start && end && end <= start) { setError('离店日期需要晚于入住日期。'); setBusy(false); return }
    const params = new URLSearchParams(window.location.search)
    try {
      const response = await fetch('/api/local-os/operations/inquiries', {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Yantian-Local': '1' },
        body: JSON.stringify({ label: fields.get('label'), notes: fields.get('notes') || '',
          ...(start ? { start_date: start } : {}), ...(end ? { end_date: end } : {}),
          people: Number(fields.get('people')), channel_id: 'direct',
          source_code: (params.get('source') || 'direct-site-preview').slice(0, 100) }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请检查填写内容后再提交。')
      setSuccess('咨询意向已保存到 OS 的渠道线索。房源、报价与体验安排仍需管理者确认。')
      form.reset()
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存失败，请稍后再试。') }
    finally { setBusy(false) }
  }
  return (
    <main className="min-h-screen bg-[#f7f5ee] text-[#263d35]">
      <div className="border-b border-[#d7ded3] bg-[#edf0e8] px-5 py-3 text-center text-xs leading-5">本地独立站预览 · 尚未公开上线 · 提交咨询不构成订房或付款</div>
      <div className="mx-auto max-w-6xl px-5 pb-16 sm:px-8">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-[#d7ded3] py-6">
          <Link href="/" className="text-xl font-semibold tracking-widest">严田庄园</Link>
          <Link href="/operations" className="flex items-center gap-2 text-sm"><ArrowLeft size={15} />返回 OS 运营台</Link>
        </header>
        <section className="grid gap-9 py-14 sm:py-20 lg:grid-cols-[1.3fr_1fr] lg:items-center">
          <div>
            <p className="text-xs tracking-[.3em] text-[#6b7d69]">YANTIAN · STAY & EXPERIENCE</p>
            <h1 className="mt-6 font-serif text-4xl leading-[1.4] sm:text-6xl">住下来，<br />慢慢认识严田。</h1>
            <p className="mt-6 max-w-lg text-sm leading-8 text-[#657266]">从一晚住宿开始，了解文化、手艺与村落日常。先告诉我们你的日期与想法，再一起确认合适的房间和行程。</p>
            <a href="#inquiry" className="mt-8 inline-flex items-center gap-8 rounded-full bg-[#284d3f] px-6 py-3 text-sm text-white">询问日期与安排 <ArrowUpRight size={17} /></a>
          </div>
          <div className="relative rounded-t-[100px] rounded-b-3xl border border-[#d1d9cc] bg-[#e4e9dc] px-7 py-12 sm:px-10">
            <Leaf size={54} strokeWidth={1} className="mb-12 text-[#839279]" />
            <p className="text-xs tracking-widest text-[#6b7d69]">管理者提供的庄园资料</p>
            <div className="mt-5 flex flex-wrap items-end gap-4"><span className="font-serif text-5xl">{catalog?.settings.room_capacity ?? '—'}</span><span className="pb-1 text-sm">间自有客房</span></div>
            <p className="mt-6 text-sm">{catalog ? `淡季住宿参考 ¥${money(catalog.settings.reference_price_cents)} / 间夜` : '正在读取参考资料'}</p>
            <p className="mt-3 text-xs leading-6 text-[#657266]">总房量不代表指定日期的可售库存。具体房型、价格、包含项目与退改条件，以管理者确认的订单为准。</p>
          </div>
        </section>
        <section className="border-t border-[#d7ded3] py-10">
          <div className="flex flex-wrap items-end justify-between gap-3"><h2 className="font-serif text-2xl">住宿与体验</h2><a href="/studio/#knowledge" className="flex items-center gap-2 text-xs text-[#657266]"><BookOpen size={14} />文化知识与出处</a></div>
          {catalog && catalog.products.length === 0 ? <div className="mt-6 rounded-2xl border border-dashed border-[#cbd4c6] p-7 text-sm leading-7 text-[#657266]">商品正在整理。你可以先提交住宿意向；体验须待接待人员、场次与容量确认后开放。</div> : <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{catalog?.products.map(product => <article key={product.id} className="rounded-2xl border border-[#d7ded3] bg-white/60 p-6"><BedDouble size={24} strokeWidth={1.3} /><p className="mt-5 text-xs text-[#71806d]">{{ stay: '住宿', experience: '体验', bundle: '住宿 + 体验' }[product.kind] || '庄园商品'}</p><h3 className="mt-2 text-xl">{product.title}</h3><p className="mt-3 whitespace-pre-wrap break-words text-sm leading-7 text-[#657266]">{product.description || '具体包含项目请咨询管理者。'}</p><p className="mt-5 text-sm">{product.price_cents == null ? '价格待确认' : `标示参考 ¥${money(product.price_cents)} · 具体日期另确认`}</p><a href="#inquiry" className="mt-4 inline-flex items-center gap-3 text-sm underline underline-offset-4">咨询安排 <ArrowUpRight size={14} /></a></article>)}</div>}
        </section>
        <section id="inquiry" className="grid scroll-mt-5 gap-8 rounded-3xl bg-[#edf0e8] p-6 sm:p-10 md:grid-cols-2">
          <div><CalendarDays size={28} strokeWidth={1.2} /><h2 className="mt-6 font-serif text-2xl">先约一个日期</h2><p className="mt-4 text-sm leading-8 text-[#657266]">这里只登记咨询意向。提交后，管理者可以在严田 OS 查看来源、核对库存，并给出具体报价。</p><p className="mt-6 text-xs leading-6 text-[#657266]">当前为本机演练入口，未连接短信、微信、平台账号或支付。请勿在本地预览填写证件、银行卡等敏感资料。</p></div>
          <form onSubmit={inquire} className="space-y-4">
            <label className="block text-sm">如何称呼你<input name="label" required maxLength={100} className="mt-2 w-full rounded-lg border border-[#cbd4c6] bg-white p-3 text-sm" placeholder="称呼或咨询代号" /></label>
            <div className="grid grid-cols-2 gap-3"><label className="block text-sm">入住日期<input type="date" name="start_date" className="mt-2 w-full min-w-0 rounded-lg border border-[#cbd4c6] bg-white p-3 text-sm" /></label><label className="block text-sm">离店日期<input type="date" name="end_date" className="mt-2 w-full min-w-0 rounded-lg border border-[#cbd4c6] bg-white p-3 text-sm" /></label></div>
            <label className="block text-sm">出行人数<input type="number" name="people" min={1} max={100} defaultValue={2} required className="mt-2 w-full rounded-lg border border-[#cbd4c6] bg-white p-3 text-sm" /></label>
            <label className="block text-sm">需求与联系备注<textarea name="notes" maxLength={2000} rows={3} className="mt-2 w-full rounded-lg border border-[#cbd4c6] bg-white p-3 text-sm" placeholder="想了解的房型、同行情况或体验；联系方式可待线下补充" /></label>
            <div aria-live="polite">{error && <p role="alert" className="text-sm text-red-700">{error}</p>}{success && <p role="status" className="flex gap-2 text-sm leading-6 text-emerald-800"><CheckCircle2 size={19} className="shrink-0" />{success}</p>}</div>
            <button disabled={busy || !catalog} className="w-full rounded-full bg-[#284d3f] px-6 py-3 text-sm text-white disabled:opacity-50">{busy ? '正在保存' : '保存咨询意向'}</button>
          </form>
        </section>
        <footer className="pt-10 text-xs text-[#71806d]">严田 OS · 住宿与体验的本地运营预览</footer>
      </div>
    </main>
  )
}
