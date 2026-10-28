export const WORKSPACE_API = '/api/local-os/workspace'

export interface AttachmentDTO {
  id: string
  name: string
  kind: 'photo' | 'document'
  media_type: string
  size_bytes: number
  sha256: string
  preview_url?: string
  read_status: 'text_extracted' | 'visual_reference' | 'unreadable'
  summary: string
  topics: string[]
  date_hints: string[]
  warnings: string[]
  integrity_state?: 'valid' | 'missing_or_changed'
}
export interface SelectedAttachment {
  key: string
  name: string
  file?: File
  local_preview?: string
  state: 'uploading' | 'ready' | 'failed'
  attachment?: AttachmentDTO
  error?: string
}
export interface RoomWindow {
  id: string
  start_date: string
  end_date: string
  room_types?: string[]
  days?: number
  verification_required?: boolean
}
export interface RoomReference { snapshot_id: string; opportunity_id: string }
export interface CreateRoute {
  id: string
  title: string
  status: string
  summary?: string
  source_refs?: unknown[]
  [key: string]: unknown
}
export interface WorkspaceSnapshot {
  plans: PlanDTO[]
  attachments: AttachmentDTO[]
  reference_summary: {
    create_routes?: CreateRoute[]
    room_status?: { id?: string; snapshot_id?: string; opportunities?: RoomWindow[]; [key: string]: unknown } | null
    [key: string]: unknown
  }
}
export interface PlanDTO {
  id: string
  version: number
  hash: string
  status: 'draft' | 'confirmed'
  confirmation_valid: boolean
  source_stale: boolean
  superseded: boolean
  blockers: string[]
  created_at: string
  request: { brief: string; attachment_ids: string[] }
  room_status_ref?: RoomReference | null
  plan: {
    title: string
    one_line_strategy: string
    objective: unknown
    date_focus: unknown
    audiences: Array<{ name: string; rationale: string; state: 'hypothesis' }>
    offering: {
      stay_statement: string
      experience_candidates: Array<{ id: string; title: string; positioning: string; status: string; checklist: string[]; source_refs: Array<{ title: string; locator: string; evidence_state: string }> }>
      price_note: string
    }
    channels: Array<{ id: string; title: string; role: string; actions: string[]; readiness: string }>
    actions: Array<{ step: string | number; title: string; description: string; owner: string; completion_evidence: unknown }>
    materials_needed: unknown[]
    checks: unknown[]
    sources: Array<{ kind: string; title: string; locator: string; evidence_state: string }>
    assumptions: unknown[]
  }
}

export async function workspaceRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${WORKSPACE_API}${path}`, {
    ...init,
    cache: 'no-store',
    headers: { 'X-Yantian-Local': '1', ...init?.headers },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail
      : Array.isArray(body.detail) ? body.detail.map((item: { msg?: string }) => item.msg || '输入格式待检查').join('；')
        : `操作暂未完成（${response.status}），请稍后重试。`
    throw new Error(detail)
  }
  return body as T
}
export function postJSON<T>(path: string, body: unknown) {
  return workspaceRequest<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}
export function describe(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(describe).filter(Boolean).join('；')
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    const preferred = ['text', 'description', 'message', 'note', 'title', 'label', 'objective', 'summary']
    const selected = preferred.map(key => record[key]).find(item => typeof item === 'string' && item)
    return selected ? String(selected) : Object.values(record).map(describe).filter(Boolean).join(' · ')
  }
  return ''
}
export function localPreview(url?: string): string | undefined { return url?.startsWith('/') && !url.startsWith('//') ? url : undefined }
export function dateLabel(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' }).format(date)
}
export function roomDateLabel(window: RoomWindow) { return window.start_date === window.end_date ? window.start_date : `${window.start_date} 至 ${window.end_date}` }
export function evidenceLabel(value: string) {
  const labels: Record<string, string> = {
    LOCAL_IMPLEMENTED_CATALOG: '本机已配置目录 · 交付待核',
    USER_CONFIRMED_EXISTING: '用户确认产品存在',
    NOT_EXECUTED: '尚无执行记录',
    PLANNING_PROPOSAL: '方案参考',
    ASSUMPTION: '测算假设',
    local_config_reference: '本机配置参考',
    user_confirmed_scope_not_current_inventory: '用户确认产品方向 · 非当期库存',
    sanitized_topic_and_date_clues_only: '附件脱敏主题与日期线索',
    source_observation_not_sellable_inventory: '源表观察 · 非已核可售库存',
  }
  return labels[value] || value
}
