'use client'
import { FormEvent, useEffect, useState } from 'react'
import { Availability, Product, TabProps, kindNames } from './types'
import { Action, Check, Empty, Field, Notice, Panel, Pill, Submit, cents, dateTime, inputClass, money, readAPI } from './ui'

export function RoomsTab({ data, mutate, busy }: TabProps) {
  const [range, setRange] = useState({ start_date: '', end_date: '' })
  const [availability, setAvailability] = useState<Availability | null>(null)
  const [queryError, setQueryError] = useState('')
  const [querying, setQuerying] = useState(false)
  useEffect(() => { setAvailability(null) }, [data.rooms, data.blocks, data.orders])
  async function query(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setQuerying(true); setQueryError(''); try { setAvailability(await readAPI<Availability>(`/availability?${new URLSearchParams(range)}`)) } catch (error) { setQueryError(error instanceof Error ? error.message : '查询未完成') } finally { setQuerying(false) } }
  return <div className="space-y-5">
    <Notice>项目声明容量 {data.settings.room_capacity} 间；当前仅 {data.rooms.length} 间已建档。未建档、停用、封房或订单占用都不能当作可售房。离店日与封房结束日不计占用。</Notice>
    <div className="grid gap-5 lg:grid-cols-[1fr_1.6fr]">
      <Panel title="登记实际客房" note="按真实房间清单建档，不自动生成房号。"><form className="space-y-4" onSubmit={async event => { event.preventDefault(); const form = event.currentTarget; const values = Object.fromEntries(new FormData(form)); if (await mutate('/rooms', values)) form.reset() }}>
        <Field label="内部房号 *"><input name="code" required maxLength={60} className={inputClass} placeholder="填写实际房号" /></Field>
        <Field label="客房名称 *"><input name="name" required maxLength={120} className={inputClass} /></Field>
        <Field label="房型 *"><input name="room_type" required maxLength={120} className={inputClass} placeholder="按实际清单填写" /></Field><Submit busy={busy}>登记客房</Submit>
      </form></Panel>
      <Panel title="客房清单" note="启用表示纳入库存查询，不代表所有日期都有空房。">
        {!data.rooms.length ? <Empty>尚无实际客房档案。<br />请先核对房间清单，再登记。</Empty> : <div className="divide-y divide-stone-100">{data.rooms.map(room => <div key={room.id} className="flex items-center justify-between gap-3 py-3"><div><div className="text-sm font-medium">{room.code} · {room.name}</div><div className="mt-1 text-xs text-stone-400">{room.room_type}</div></div><div className="flex items-center gap-2"><Pill tone={room.enabled ? 'green' : 'neutral'}>{room.enabled ? '已启用' : '已停用'}</Pill><Action disabled={busy} onClick={() => mutate(`/rooms/${room.id}`, { enabled: !room.enabled }, 'PATCH')}>{room.enabled ? '停用' : '启用'}</Action></div></div>)}</div>}
      </Panel>
    </div>
    <Panel title="按日期查询房态" note="查询结果来自已建档客房、有效封房及当前订单；房量随日期变化。">
      <form onSubmit={query} className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]"><Field label="开始 / 入住日 *"><input type="date" required value={range.start_date} onChange={event => { setRange({ ...range, start_date: event.target.value }); setAvailability(null) }} className={inputClass} /></Field><Field label="结束 / 离店日 *"><input type="date" required min={range.start_date || undefined} value={range.end_date} onChange={event => { setRange({ ...range, end_date: event.target.value }); setAvailability(null) }} className={inputClass} /></Field><Submit busy={querying}>查询可售房</Submit></form>
      {queryError && <p role="alert" className="mt-3 text-xs text-red-700">{queryError}</p>}
      {availability && <div className="mt-5"><div className="mb-3 flex flex-wrap gap-2"><Pill tone="green">本日期范围可售 {availability.available_rooms} 间</Pill><Pill>已建档 {availability.registered_rooms} 间</Pill><Pill tone="amber">未建档 {availability.unregistered_rooms} 间不计可售</Pill></div><div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{availability.rooms.map(room => <div key={room.id} className={`rounded-xl border p-3 ${room.available ? 'border-emerald-100 bg-emerald-50/50' : 'border-stone-200 bg-stone-50'}`}><div className="flex justify-between gap-2 text-xs"><strong>{room.code} · {room.name}</strong><span>{room.available ? '可售' : '不可售'}</span></div><p className="mt-1 text-[11px] text-stone-500">{room.available ? room.room_type : room.conflicts.map(conflict => conflict.reason).join('；')}</p></div>)}</div>{!availability.rooms.length && <Empty>尚未建档任何客房，不能按声明容量生成可售房。</Empty>}</div>}
    </Panel>
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel title="登记维修 / 经营封房" note="封房期间阻止新订单占用，不改写已有房间记录。"><form className="space-y-4" onSubmit={async event => { event.preventDefault(); const form = event.currentTarget; if (await mutate('/blocks', Object.fromEntries(new FormData(form)))) form.reset() }}><Field label="实际客房 *"><select name="room_id" required className={inputClass} defaultValue=""><option value="">选择客房</option>{data.rooms.map(room => <option key={room.id} value={room.id}>{room.code} · {room.name}</option>)}</select></Field><div className="grid grid-cols-2 gap-3"><Field label="封房开始日 *"><input name="start_date" type="date" required className={inputClass} /></Field><Field label="封房结束日 *" hint="该日不占用"><input name="end_date" type="date" required className={inputClass} /></Field></div><Field label="原因 *"><input name="reason" required maxLength={300} className={inputClass} placeholder="维修、停业或其他实际原因" /></Field><Submit busy={busy}>登记封房</Submit></form></Panel>
      <Panel title="封房记录" note="释放后记录仍保留。">{!data.blocks.length ? <Empty>尚无封房记录。</Empty> : <div className="divide-y divide-stone-100">{[...data.blocks].reverse().map(block => <div key={block.id} className="py-3"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-medium">{data.rooms.find(room => room.id === block.room_id)?.code || '关联客房'} · {block.reason}</p><p className="mt-1 text-xs text-stone-400">{block.start_date} 至 {block.end_date}（不含结束日）</p></div>{block.status === 'active' ? <Action disabled={busy} onClick={() => mutate(`/blocks/${block.id}/release`, {})}>释放封房</Action> : <Pill>已释放</Pill>}</div></div>)}</div>}</Panel>
    </div>
  </div>
}

export function ProductsTab({ data, mutate, busy }: TabProps) {
  const [editing, setEditing] = useState<Product | null>(null)
  const [kind, setKind] = useState<Product['kind']>('stay')
  const [productStatus, setProductStatus] = useState<Product['status']>('draft')
  const deliveryRequired = kind !== 'stay' && productStatus === 'active'
  function edit(product: Product | null) { setEditing(product); setKind(product?.kind || 'stay'); setProductStatus(product?.status || 'draft') }
  const sessionProducts = data.products.filter(product => product.kind !== 'stay' && product.status === 'active' && product.delivery_confirmed)
  return <div className="space-y-5">
    <Notice>住宿价格由经营者逐单报价。体验和套餐的负责人、时长及交付能力未确认时，只能保留草稿；不因为有文化知识或图样，就默认能够接待。</Notice>
    <div className="grid gap-5 lg:grid-cols-[1fr_1.2fr]">
      <Panel title={editing ? '编辑产品' : '建立产品草稿'} note="价格可待定；启用条件由本地服务再次核对。" action={editing ? <Action onClick={() => edit(null)}>新建产品</Action> : undefined}>
        <form key={editing?.id || 'new'} className="space-y-4" onSubmit={async event => { event.preventDefault(); const form = event.currentTarget; const fields = new FormData(form); const payload = { title: fields.get('title'), kind, price_cents: fields.get('price') === '' ? null : cents(fields.get('price')), status: fields.get('status'), description: fields.get('description'), delivery_confirmed: fields.has('delivery_confirmed'), facilitator: fields.get('facilitator') || '', duration_minutes: fields.get('duration_minutes') === '' ? null : Number(fields.get('duration_minutes')) }; if (await mutate(editing ? `/products/${editing.id}` : '/products', payload, editing ? 'PUT' : 'POST')) { form.reset(); edit(null) } }}>
          <Field label="产品名称 *"><input name="title" required defaultValue={editing?.title || ''} maxLength={160} className={inputClass} /></Field>
          <div className="grid grid-cols-2 gap-3"><Field label="产品类型 *"><select value={kind} onChange={event => setKind(event.target.value as Product['kind'])} className={inputClass}>{Object.entries(kindNames).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></Field><Field label="产品状态 *"><select name="status" value={productStatus} onChange={event => setProductStatus(event.target.value as Product['status'])} className={inputClass}><option value="draft">草稿 / 待确认</option><option value="active">启用</option></select></Field></div>
          <Field label="参考产品价 / 元" hint="可留空；不作为所有日期的最终报价"><input name="price" type="number" min="0" step="0.01" defaultValue={editing?.price_cents == null ? '' : editing.price_cents / 100} className={inputClass} /></Field>
          <Field label="产品说明"><textarea name="description" rows={3} defaultValue={editing?.description || ''} className={inputClass} placeholder="仅填写可验证的产品内容" /></Field>
          <div className="grid grid-cols-2 gap-3"><Field label={deliveryRequired ? '交付负责人 *' : '负责人（待确认可留空）'}><input name="facilitator" required={deliveryRequired} defaultValue={editing?.facilitator || ''} className={inputClass} /></Field><Field label={deliveryRequired ? '体验时长 / 分钟 *' : '时长 / 分钟（待确认可留空）'}><input name="duration_minutes" required={deliveryRequired} type="number" min="1" step="1" defaultValue={editing?.duration_minutes ?? ''} className={inputClass} /></Field></div>
          <Check name="delivery_confirmed" checked={editing?.delivery_confirmed || undefined}>我已核对本产品实际交付能力（新产品不默认确认）。</Check>
          <Submit busy={busy}>{editing ? '保存产品修改' : '保存产品'}</Submit>
        </form>
      </Panel>
      <Panel title="住宿与体验目录" note="只有启用的产品可用于新订单。"><div className="space-y-3">{!data.products.length ? <Empty>还没有住宿或体验产品。<br />先核对交付条件，再建立第一项。</Empty> : data.products.map(product => <article key={product.id} className="rounded-xl border border-stone-200 p-4"><div className="flex justify-between gap-3"><div><h3 className="text-sm font-semibold">{product.title}</h3><div className="mt-2 flex flex-wrap gap-2"><Pill>{kindNames[product.kind]}</Pill><Pill tone={product.status === 'active' ? 'green' : 'amber'}>{product.status === 'active' ? '已启用' : '草稿'}</Pill>{product.kind !== 'stay' && <Pill tone={product.delivery_confirmed ? 'green' : 'amber'}>{product.delivery_confirmed ? '已确认交付' : '交付待确认'}</Pill>}</div></div><Action onClick={() => edit(product)}>编辑</Action></div><p className="mt-3 whitespace-pre-wrap text-xs leading-6 text-stone-500">{product.description || '尚无产品说明'}</p><p className="mt-2 text-xs text-stone-500">产品参考价：{product.price_cents == null ? '待报价' : money(product.price_cents)}{product.facilitator ? ` · 负责人：${product.facilitator}` : ''}{product.duration_minutes ? ` · ${product.duration_minutes} 分钟` : ''}</p></article>)}</div><div className="mt-4 flex flex-wrap gap-4 text-xs text-emerald-800"><a href="/studio/#knowledge" className="underline">复用文化知识 ↗</a><a href="/studio/#designs" className="underline">查看木刻稿样 ↗</a></div></Panel>
    </div>
    <div className="grid gap-5 lg:grid-cols-2">
      <Panel title="安排已确认的体验场次" note="场次还需单独确认交付；容量是此场上限，不是已报名人数。"><form className="space-y-4" onSubmit={async event => { event.preventDefault(); const form = event.currentTarget; const fields = new FormData(form); const payload = { product_id: fields.get('product_id'), starts_at: `${fields.get('starts_at')}:00+08:00`, capacity: Number(fields.get('capacity')), delivery_confirmed: fields.has('delivery_confirmed') }; if (await mutate('/sessions', payload)) form.reset() }}><Field label="体验 / 套餐产品 *"><select name="product_id" defaultValue="" required className={inputClass}><option value="">选择已启用且确认交付的产品</option>{sessionProducts.map(product => <option key={product.id} value={product.id}>{product.title}</option>)}</select></Field><div className="grid grid-cols-2 gap-3"><Field label="开始时间（北京时间）*"><input name="starts_at" type="datetime-local" required className={inputClass} /></Field><Field label="场次容量 / 人 *"><input name="capacity" type="number" min="1" step="1" required className={inputClass} /></Field></div><Check name="delivery_confirmed">我已确认此时间、场地及负责人可以交付。</Check><Submit busy={busy}>保存场次</Submit></form></Panel>
      <Panel title="场次与名额" note="订单暂留也占用名额；实时余量以提交时再次核验为准。">{!data.sessions.length ? <Empty>尚未安排任何可交付场次。</Empty> : <div className="divide-y divide-stone-100">{data.sessions.map(session => <div key={session.id} className="py-3"><div className="flex justify-between gap-3"><h3 className="text-sm font-medium">{data.products.find(product => product.id === session.product_id)?.title || '关联产品'}</h3><Pill tone={session.available ? 'green' : 'amber'}>{session.available ? '可预订' : '暂不可预订'}</Pill></div><p className="mt-2 text-xs text-stone-500">{dateTime(session.starts_at)} · 容量 {session.capacity} 人 · 已占 {session.booked_seats} · 余 {session.remaining_capacity}</p></div>)}</div>}</Panel>
    </div>
  </div>
}
