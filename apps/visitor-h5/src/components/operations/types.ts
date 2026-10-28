export interface Room { id: string; code: string; name: string; room_type: string; enabled: boolean; created_at: string }
export interface Block { id: string; room_id: string; start_date: string; end_date: string; reason: string; status: 'active' | 'released'; created_at: string }
export interface Product { id: string; title: string; kind: 'stay' | 'experience' | 'bundle'; price_cents: number | null; status: 'draft' | 'active'; description: string; delivery_confirmed: boolean; facilitator: string; duration_minutes: number | null }
export interface Session { id: string; product_id: string; starts_at: string; capacity: number; delivery_confirmed: boolean; booked_seats: number; remaining_capacity: number; available: boolean }
export interface Lead { id: string; label: string; channel_id: string; source_code: string; notes: string; status: 'new' | 'contacted' | 'quoted' | 'booked' | 'lost'; start_date?: string; end_date?: string; people?: number }
export interface ContentDraft { id: string; title: string; channel_id: string; body: string; source_code: string; product_id?: string; created_at: string }
export interface Order { id: string; label: string; product_id: string; product_snapshot: Product; kind: Product['kind']; room_ids: string[]; start_date: string | null; end_date: string | null; session_id: string | null; seats: number; amount_cents: number; channel_id: string; source_code: string; lead_id: string | null; expires_at: string; created_at: string; status: 'hold' | 'confirmed' | 'fulfilled' | 'cancelled' | 'expired'; payment_status: string; received_cents: number; refunded_cents: number; net_received_cents: number; manual_receipt_recorded: boolean }
export interface Payment { id: string; order_id: string; amount_cents: number; receipt_ref: string; created_at: string }
export interface Channel { id?: string; channel_id?: string; name?: string; label?: string; status?: string; note?: string; connected?: boolean; connection_state?: string; platform_connected?: boolean }
export interface Snapshot {
  settings: { property_name: string; room_capacity: number; reference_price_cents: number; season: string; provenance: unknown }
  channels: Channel[]; rooms: Room[]; blocks: Block[]; products: Product[]; sessions: Session[]; leads: Lead[]; content_drafts: ContentDraft[]; orders: Order[]; payments: Payment[]; refunds: Payment[]
  summary: { rooms_registered: number; rooms_enabled: number; unregistered_rooms: number; orders_count: number; active_orders: number; hold_orders: number; confirmed_orders: number; fulfilled_orders: number; cancelled_orders: number; expired_orders: number; payments_count: number; refunds_count: number; quoted_total_cents: number; received_cents: number | null; refunded_cents: number | null; net_received_cents: number | null; cash_record_state: string; revenue_cents: null; revenue_state: string; note: string }
}
export interface Availability { start_date: string; end_date: string; rooms: Array<Room & { available: boolean; conflicts: Array<{ kind: string; id: string | null; reason: string }> }>; available_rooms: number; registered_rooms: number; unregistered_rooms: number; declared_room_capacity: number }
export type Mutate = (path: string, payload?: unknown, method?: 'POST' | 'PATCH' | 'PUT') => Promise<boolean>
export interface TabProps { data: Snapshot; mutate: Mutate; busy: boolean }
export const channelOptions = [['direct', '直营 / 线下'], ['xiaohongshu', '小红书'], ['douyin', '抖音'], ['other', '其他来源']] as const
export const channelName = (id: string) => channelOptions.find(([key]) => key === id)?.[1] || id
export const kindNames = { stay: '住宿', experience: '体验', bundle: '住宿 + 体验' }
export const orderStates: Record<string, string> = { hold: '暂留中', confirmed: '已确认', fulfilled: '已履约', cancelled: '已取消', expired: '已过期' }
export const leadStates: Record<string, string> = { new: '新咨询', contacted: '已联系', quoted: '已报价', booked: '已转订单', lost: '未成交' }
