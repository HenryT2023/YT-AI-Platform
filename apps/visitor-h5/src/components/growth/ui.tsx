'use client'
export { Action, Check, Empty, Field, Notice, Panel, Pill, Submit, dateTime, inputClass, money } from '@/components/operations/ui'
export const GROWTH_API = '/api/local-os/growth'
export function localAssetUrl(value?: string) { return value?.startsWith(`${GROWTH_API}/`) ? value : null }
export function readable(value: unknown): string { if (value == null) return '待核对'; if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value); if (typeof value === 'object' && 'text' in value) { const claim = value as { text: unknown; basis?: unknown; scope?: unknown }; return `${String(claim.text)}${claim.basis ? `（依据：${String(claim.basis)}）` : ''}${claim.scope ? `；范围：${String(claim.scope)}` : ''}` }; return JSON.stringify(value) }
export function isApproved(packageId: string, hash: string, reviews: Array<{ package_id: string; package_hash: string; decision: string }>) { const matches = reviews.filter(review => review.package_id === packageId && review.package_hash === hash); return matches.length > 0 && matches[matches.length - 1].decision === 'approve' }
