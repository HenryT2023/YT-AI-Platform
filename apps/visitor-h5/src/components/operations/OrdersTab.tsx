'use client'
import { FormEvent, useEffect, useState } from 'react'
import { Availability, Mutate, Order, Snapshot, TabProps, channelName, channelOptions, kindNames, orderStates } from './types'
import { Action, Check, Empty, Field, Notice, Panel, Pill, Submit, cents, dateTime, inputClass, money, readAPI, useIdempotency } from './ui'

const paymentNames: Record<string, string> = { unpaid: '未登记收款', partial: '部分登记收款', paid: '足额已登记', partially_refunded: '部分退款已登记', refunded: '全额退款已登记' }

function NewOrder({ data, mutate, busy }: TabProps) {
  const [productId, setProductId] = useState('')
  const [dates, setDates] = useState({ start_date: '', end_date: '' })
  const [availability, setAvailability] = useState<Availability | null>(null)
  const [selectedRooms, setSelectedRooms] = useState<string[]>([])
  const [channel, setChannel] = useState('direct')
  const [sourceCode, setSourceCode] = useState('')
  const [error, setError] = useState('')
  const [querying, setQuerying] = useState(false)
  const idempotency = useIdempotency()
  const product = data.products.find(item => item.id === productId)
  const needsStay = product?.kind === 'stay' || product?.kind === 'bundle'
  const needsExperience = product?.kind === 'experience' || product?.kind === 'bundle'
  const activeProducts = data.products.filter(item => item.status === 'active' && (item.kind === 'stay' || item.delivery_confirmed))
  const sessions = data.sessions.filter(session => session.product_id === productId && session.available)
  useEffect(() => { setAvailability(null); setSelectedRooms([]) }, [data.rooms, data.blocks, data.orders])
  function changeDate(key: 'start_date' | 'end_date', value: string) { setDates({ ...dates, [key]: value }); setAvailability(null); setSelectedRooms([]) }
  async function queryRooms() {
    if (!dates.start_date || !dates.end_date || dates.end_date <= dates.start_date) { setError('请填写有效的入住与离店日期，离店日须晚于入住日。'); return }
    setQuerying(true); setError('')
    try { setAvailability(await readAPI<Availability>(`/availability?${new URLSearchParams(dates)}`)); setSelectedRooms([]) } catch (cause) { setError(cause instanceof Error ? cause.message : '房态查询未完成') } finally { setQuerying(false) }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('')
    if (!product) { setError('请选择已启用产品。'); return }
    if (needsStay && (!availability || !selectedRooms.length)) { setError('请先查询本次日期的可售房，再勾选实际客房。'); return }
    const form = event.currentTarget; const fields = new FormData(form)
    const payload = { label: fields.get('label'), product_id: productId, room_ids: needsStay ? selectedRooms : [], ...(needsStay ? dates : {}), ...(needsExperience ? { session_id: fields.get('session_id') } : {}), seats: needsExperience ? Number(fields.get('seats')) : 0, amount_cents: cents(fields.get('amount')), channel_id: channel, source_code: sourceCode, ...(fields.get('lead_id') ? { lead_id: fields.get('lead_id') } : {}), hold_minutes: 30 }
    if (await mutate('/orders', { ...payload, idempotency_key: idempotency.keyFor(payload) })) { idempotency.reset(); form.reset(); setProductId(''); setDates({ start_date: '', end_date: '' }); setAvailability(null); setSelectedRooms([]); setSourceCode(''); setChannel('direct') }
  }
  return <Panel title="登记订单与暂留库存" note="正式金额由经营者人工确认。新订单暂留30分钟；同房、同夜与场次余量由服务端再次检查。">
    <form className="space-y-4" onSubmit={submit}>
      <div className="grid gap-4 sm:grid-cols-2"><Field label="订单标签 *" hint="使用匿名业务代号，不填身份证或完整个人资料"><input name="label" required maxLength={120} className={inputClass} /></Field><Field label="已启用产品 *"><select value={productId} required onChange={event => { setProductId(event.target.value); setAvailability(null); setSelectedRooms([]) }} className={inputClass}><option value="">请选择产品</option>{activeProducts.map(item => <option key={item.id} value={item.id}>{kindNames[item.kind]} · {item.title}</option>)}</select></Field></div>
      {product && <div className="rounded-lg bg-stone-50 px-3 py-2 text-xs leading-6 text-stone-500">{product.title} · 产品参考价 {product.price_cents == null ? '待定' : money(product.price_cents)}。本单总金额仍需手工填写，不按容量或参考房价推算。</div>}
      {needsStay && <div className="space-y-3 rounded-xl border border-stone-200 p-4"><h3 className="text-xs font-semibold text-stone-600">住宿库存</h3><div className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]"><Field label="入住日 *"><input type="date" required value={dates.start_date} onChange={event => changeDate('start_date', event.target.value)} className={inputClass} /></Field><Field label="离店日 *" hint="离店日不计房晚"><input type="date" required min={dates.start_date || undefined} value={dates.end_date} onChange={event => changeDate('end_date', event.target.value)} className={inputClass} /></Field><Action onClick={queryRooms} disabled={querying}>{querying ? '正在查询…' : '查询可售房'}</Action></div>
        {availability && <><div className="text-xs text-stone-500">本次可售 {availability.available_rooms} 间；仅勾选本订单实际需要的客房。</div><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{availability.rooms.filter(room => room.available).map(room => <div key={room.id} className="rounded-lg border border-emerald-100 bg-emerald-50/50 px-3 py-2"><Check checked={selectedRooms.includes(room.id)} onChange={checked => setSelectedRooms(previous => checked ? [...previous, room.id] : previous.filter(id => id !== room.id))}>{room.code} · {room.name}<span className="block text-[10px] text-stone-400">{room.room_type}</span></Check></div>)}</div>{availability.available_rooms === 0 && <Empty>这些日期没有已建档且可售的客房。请调整日期，或核对实际房态。</Empty>}</>}
      </div>}
      {needsExperience && <div className="grid gap-4 rounded-xl border border-stone-200 p-4 sm:grid-cols-[2fr_1fr]"><Field label="已确认交付的场次 *"><select name="session_id" required defaultValue="" className={inputClass}><option value="">选择可预订场次</option>{sessions.map(session => <option key={session.id} value={session.id}>{dateTime(session.starts_at)} · 余 {session.remaining_capacity}/{session.capacity} 人</option>)}</select></Field><Field label="本次人数 *"><input name="seats" type="number" min="1" step="1" required className={inputClass} /></Field>{!sessions.length && <p className="text-xs text-amber-800 sm:col-span-2">该产品尚无可预订场次，请先在“住宿与体验”核对交付并安排。</p>}</div>}
      <div className="grid gap-4 sm:grid-cols-2"><Field label="本单人工报价总额 / 元 *" hint="零金额订单须在保存后单独确认"><input name="amount" type="number" required min="0" step="0.01" className={inputClass} placeholder="填写双方已确认金额" /></Field><Field label="关联咨询（可选）"><select name="lead_id" defaultValue="" onChange={event => { const lead = data.leads.find(item => item.id === event.target.value); if (lead) { setChannel(lead.channel_id); setSourceCode(lead.source_code) } }} className={inputClass}><option value="">不关联咨询</option>{data.leads.map(lead => <option key={lead.id} value={lead.id}>{lead.label}</option>)}</select></Field><Field label="来源渠道 *"><select value={channel} onChange={event => setChannel(event.target.value)} className={inputClass}>{channelOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></Field><Field label="来源码 *"><input required maxLength={100} value={sourceCode} onChange={event => setSourceCode(event.target.value)} className={inputClass} /></Field></div>
      {error && <p role="alert" className="text-xs text-red-700">{error}</p>}<Submit busy={busy}>保存订单并暂留30分钟</Submit>
    </form>
  </Panel>
}

function MoneyForm({ order, mode, mutate, busy }: { order: Order; mode: 'payments' | 'refunds'; mutate: Mutate; busy: boolean }) {
  const idempotency = useIdempotency()
  const available = mode === 'payments' ? order.amount_cents - order.received_cents : order.net_received_cents
  return <form className="space-y-3 rounded-xl border border-stone-200 bg-stone-50 p-4" onSubmit={async event => { event.preventDefault(); const form = event.currentTarget; const fields = new FormData(form); const payload = { amount_cents: cents(fields.get('amount')), receipt_ref: fields.get('receipt_ref') }; if (await mutate(`/orders/${order.id}/${mode}`, { ...payload, idempotency_key: idempotency.keyFor(payload) })) { idempotency.reset(); form.reset() } }}>
    <h4 className="text-xs font-semibold">{mode === 'payments' ? '人工登记已收到的款项' : '人工登记已退回的款项'}</h4><p className="text-[11px] leading-5 text-stone-500">{mode === 'payments' ? '仅登记线下已收款记录，无在线收款或银行核验。足额登记后订单自动确认。' : '取消订单不会自动退款；仅登记已经发生的退款，不发起资金划转。'}</p>
    <div className="grid gap-3 sm:grid-cols-2"><Field label={mode === 'payments' ? '本次已登记收款 / 元 *' : '本次已登记退款 / 元 *'}><input name="amount" type="number" required min="0.01" max={Math.max(0, available) / 100} step="0.01" className={inputClass} /></Field><Field label="实际流水 / 凭据引用 *" hint="只填内部凭据编号，不填银行卡号"><input name="receipt_ref" required maxLength={200} className={inputClass} /></Field></div><Submit busy={busy}>{mode === 'payments' ? '保存收款登记' : '保存退款登记'}</Submit>
  </form>
}

function OrderCard({ order, data, mutate, busy }: { order: Order; data: Snapshot; mutate: Mutate; busy: boolean }) {
  const [cancelChecked, setCancelChecked] = useState(false)
  const canChange = order.status === 'hold' || order.status === 'confirmed'
  const receipts = data.payments.filter(payment => payment.order_id === order.id)
  const refunds = data.refunds.filter(refund => refund.order_id === order.id)
  return <details className="rounded-xl border border-stone-200 bg-white p-4 sm:p-5"><summary className="cursor-pointer list-none"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="text-sm font-semibold">{order.label}</h3><p className="mt-1 text-xs text-stone-500">{order.product_snapshot?.title || data.products.find(product => product.id === order.product_id)?.title || '关联产品'} · {channelName(order.channel_id)}</p></div><div className="flex flex-wrap items-center gap-2"><Pill tone={order.status === 'confirmed' || order.status === 'fulfilled' ? 'green' : order.status === 'hold' ? 'amber' : 'neutral'}>{orderStates[order.status]}</Pill><Pill>{paymentNames[order.payment_status] || order.payment_status}</Pill><span className="ml-2 text-sm font-semibold">{money(order.amount_cents)}</span><span className="text-xs text-stone-400">展开 ↓</span></div></div><div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-stone-400"><span>已登记收款 {money(order.received_cents)}</span><span>已登记退款 {money(order.refunded_cents)}</span><span>已登记净收款 {money(order.net_received_cents)}</span></div></summary>
    <div className="mt-5 space-y-4 border-t border-stone-100 pt-4"><div className="grid gap-2 text-xs leading-6 text-stone-500 sm:grid-cols-2"><p>订单编号：{order.id}</p><p>来源码：{order.source_code}</p>{order.start_date && <p>住宿日期：{order.start_date} 至 {order.end_date}（离店日不含）</p>}{order.room_ids.length > 0 && <p>客房：{order.room_ids.map(id => data.rooms.find(room => room.id === id)?.code || id).join('、')}</p>}{order.session_id && <p>体验场次：{dateTime(data.sessions.find(session => session.id === order.session_id)?.starts_at)} · {order.seats} 人</p>}<p>登记时间：{dateTime(order.created_at)}</p>{order.status === 'hold' && <p>暂留截至：{dateTime(order.expires_at)}</p>}</div>
      {order.status === 'hold' && order.received_cents > 0 && <Notice>本单已有部分人工收款登记，不自动释放库存。请继续核对余款，或明确取消后单独登记退款。</Notice>}
      {order.status === 'cancelled' && order.net_received_cents > 0 && <Notice>订单已取消，库存已释放；仍有已登记净收款 {money(order.net_received_cents)}，取消不代表已退款。</Notice>}
      <div className="flex flex-wrap gap-2">{order.status === 'hold' && <Action disabled={busy} onClick={() => mutate(`/orders/${order.id}/confirm`, {})}>{order.amount_cents === 0 ? '确认零金额订单' : '核对全款并确认'}</Action>}{order.status === 'confirmed' && <Action disabled={busy} onClick={() => mutate(`/orders/${order.id}/fulfill`, {})}>登记实际履约完成</Action>}</div>
      {order.status === 'confirmed' && <p className="text-[11px] leading-6 text-stone-400">仅在住宿退房 / 体验结束且实际服务已完成后登记履约；提前登记会被拒绝。历史日期与场次占用仍保留。</p>}
      {canChange && order.received_cents < order.amount_cents && <MoneyForm order={order} mode="payments" mutate={mutate} busy={busy} />}
      {order.net_received_cents > 0 && <MoneyForm order={order} mode="refunds" mutate={mutate} busy={busy} />}
      {canChange && <div className="rounded-xl border border-red-100 px-4 py-3"><Check checked={cancelChecked} onChange={setCancelChecked}>我确认取消本单并释放库存；收退款记录保留，退款另外登记。</Check><div className="mt-3"><Action danger disabled={busy || !cancelChecked} onClick={async () => { if (await mutate(`/orders/${order.id}/cancel`, {})) setCancelChecked(false) }}>取消订单并释放库存</Action></div></div>}
      <div className="space-y-2"><h4 className="text-xs font-semibold text-stone-600">人工资金登记留痕</h4>{!receipts.length && !refunds.length ? <p className="text-xs text-stone-400">本单尚无收退款登记。</p> : [...receipts.map(item => ({ ...item, direction: '收款' })), ...refunds.map(item => ({ ...item, direction: '退款' }))].map(item => <div key={`${item.direction}-${item.id}`} className="flex flex-wrap justify-between gap-2 rounded-lg bg-stone-50 px-3 py-2 text-[11px] text-stone-500"><span>{item.direction} · {money(item.amount_cents)} · 引用 {item.receipt_ref}</span><span>{dateTime(item.created_at)}</span></div>)}</div>
    </div>
  </details>
}

export default function OrdersTab(props: TabProps) {
  const [filter, setFilter] = useState('')
  const [search, setSearch] = useState('')
  const orders = props.data.orders.filter(order => (!filter || order.status === filter) && `${order.label} ${order.id} ${order.source_code}`.toLowerCase().includes(search.toLowerCase()))
  return <div className="space-y-5"><Notice>订单报价、人工收款、退款与营业收入分别记录。本地台账不会执行在线支付或退款；实际履约完成也需经营者根据事实登记。</Notice><NewOrder {...props} /><Panel title="订单台账" note="点击订单展开：核对库存、人工收退款、确认、取消与履约。"><div className="mb-4 flex flex-wrap gap-3"><input type="search" placeholder="搜索订单标签、编号或来源码" aria-label="搜索订单" value={search} onChange={event => setSearch(event.target.value)} className={`${inputClass} flex-1 basis-48`} /><select aria-label="订单状态筛选" value={filter} onChange={event => setFilter(event.target.value)} className={`${inputClass} sm:!w-40`}><option value="">全部状态</option>{Object.entries(orderStates).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></div><div className="space-y-3">{orders.length ? [...orders].reverse().map(order => <OrderCard key={order.id} order={order} {...props} />) : <Empty>{props.data.orders.length ? '没有符合当前条件的订单。' : '尚无订单记录。先确认产品、库存与报价，再登记真实订单。'}</Empty>}</div></Panel></div>
}
