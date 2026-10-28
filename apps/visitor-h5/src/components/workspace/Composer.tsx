'use client'

import { ReactNode, useRef } from 'react'
import { ArrowRight, FileText, ImagePlus, Loader2, Paperclip, RotateCcw, X } from 'lucide-react'
import { AttachmentDTO, SelectedAttachment, localPreview } from './types'
import { Tag, primaryButton, secondaryButton } from './ui'

const examples = [
  '帮我推广最近的住宿，搭配严田 CREATE 文化体验。',
  '用这几张照片，整理适合周末短住的运营方案。',
  '按最新房态的待核日期，安排住宿与文化体验推广。',
]
const readLabels = { text_extracted: '已提取文字', visual_reference: '照片参考 · 不推定画面事实', unreadable: '未能读取 · 需补充说明' }

function AttachmentCard({ item, disabled, onRemove, onRetry }: { item: SelectedAttachment; disabled: boolean; onRemove: () => void; onRetry: () => void }) {
  const attachment = item.attachment
  const preview = item.local_preview || (attachment?.kind === 'photo' ? localPreview(attachment.preview_url) : undefined)
  return <article className="relative flex min-w-0 gap-3 rounded-xl border border-stone-200 bg-stone-50/70 p-3">
    {preview ? <img src={preview} alt={`${item.name}，本次附加材料预览`} className="h-16 w-16 shrink-0 rounded-lg border border-stone-100 object-cover" /> : <div className="flex h-16 w-12 shrink-0 items-center justify-center rounded-lg bg-white text-stone-400"><FileText className="h-6 w-6" /></div>}
    <div className="min-w-0 flex-1 pr-5"><p className="truncate text-xs font-medium text-stone-700" title={item.name}>{item.name}</p>
      <p className="mt-1 text-[10px] leading-5 text-stone-400">{item.state === 'uploading' ? '正在保存并读取材料…' : item.state === 'failed' ? item.error : attachment ? readLabels[attachment.read_status] : '待读取'}</p>
      {attachment?.summary && <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-stone-500">{attachment.summary}</p>}
      {attachment?.warnings?.length ? <details className="mt-1 text-[10px] text-amber-800"><summary className="cursor-pointer">{attachment.warnings.length} 项读取提示</summary><ul className="mt-1 space-y-1">{attachment.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul></details> : null}
      {item.state === 'failed' && item.file && <button type="button" disabled={disabled} onClick={onRetry} className="mt-1 text-[11px] text-emerald-800 underline">重新上传</button>}
    </div><button type="button" disabled={disabled} onClick={onRemove} aria-label={`从本次任务移除 ${item.name}`} className="absolute right-2 top-2 rounded p-1 text-stone-400 hover:bg-stone-200 disabled:opacity-40"><X className="h-3.5 w-3.5" /></button>
  </article>
}

interface ComposerProps {
  brief: string
  setBrief: (value: string) => void
  selected: SelectedAttachment[]
  attachments: AttachmentDTO[]
  busy: boolean
  generating: boolean
  canGenerate: boolean
  editing: boolean
  onFiles: (files: FileList | null) => void
  onRemove: (key: string) => void
  onRetry: (key: string) => void
  onSelect: (attachment: AttachmentDTO) => void
  onGenerate: () => void
  context?: ReactNode
}
export default function Composer({ brief, setBrief, selected, attachments, busy, generating, canGenerate, editing, onFiles, onRemove, onRetry, onSelect, onGenerate, context }: ComposerProps) {
  const photoInput = useRef<HTMLInputElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const previousAttachments = attachments.filter(attachment => !selected.some(item => item.attachment?.id === attachment.id))
  const uploading = selected.some(item => item.state === 'uploading')
  return <section aria-labelledby="composer-title" className="min-w-0 rounded-2xl border border-stone-200 bg-white shadow-[0_5px_24px_-16px_rgba(28,50,40,.18)]">
    <form onSubmit={event => { event.preventDefault(); if (canGenerate && !busy) onGenerate() }}>
      <div className="p-5 pb-4 sm:p-7 sm:pb-5"><div className="mb-4 flex flex-wrap items-center justify-between gap-2"><label id="composer-title" htmlFor="workspace-brief" className="text-sm font-medium text-stone-700">今天想解决什么经营问题？</label>{editing && <Tag>基于此方案继续修改</Tag>}</div>
        <textarea id="workspace-brief" value={brief} onChange={event => setBrief(event.target.value)} disabled={busy} rows={4} maxLength={4000} placeholder="说一句话，或添加照片、房态表、产品资料。例如：帮我推广 11 月的住宿，搭配严田 CREATE 文化体验。" className="min-h-[136px] w-full resize-y border-0 bg-transparent p-0 text-base leading-8 text-stone-800 outline-none placeholder:text-stone-400 focus-visible:rounded focus-visible:ring-2 focus-visible:ring-emerald-100 disabled:opacity-60 sm:text-lg" />
        {context}
        {selected.length > 0 && <div className="mt-4 grid min-w-0 gap-2 sm:grid-cols-2">{selected.map(item => <AttachmentCard key={item.key} item={item} disabled={busy} onRemove={() => onRemove(item.key)} onRetry={() => onRetry(item.key)} />)}</div>}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-stone-100 px-5 py-4 sm:px-7"><div className="flex flex-wrap items-center gap-2"><button type="button" disabled={busy} onClick={() => photoInput.current?.click()} className={secondaryButton}><ImagePlus className="h-4 w-4" />添加照片</button><button type="button" disabled={busy} onClick={() => fileInput.current?.click()} className={secondaryButton}><Paperclip className="h-4 w-4" />添加附件</button><input ref={photoInput} type="file" multiple accept="image/jpeg,image/png,image/webp" className="sr-only" aria-label="选择照片" disabled={busy} onChange={event => { onFiles(event.target.files); event.target.value = '' }} /><input ref={fileInput} type="file" multiple accept=".jpg,.jpeg,.png,.webp,.txt,.md,.csv,.xlsx,.docx,.pdf" className="sr-only" aria-label="选择资料附件" disabled={busy} onChange={event => { onFiles(event.target.files); event.target.value = '' }} /></div>
        <button type="submit" disabled={!canGenerate || busy || uploading} className={`${primaryButton} w-full sm:w-auto`}>{generating ? <Loader2 className="h-4 w-4 animate-spin" /> : editing ? <RotateCcw className="h-4 w-4" /> : <ArrowRight className="h-4 w-4" />}{generating ? '正在整理运营方案…' : editing ? '生成修改后的方案' : '生成运营方案'}</button>
      </div>
    </form>
    <div className="border-t border-stone-100 bg-stone-50/50 px-5 py-3 text-[10px] leading-5 text-stone-400 sm:px-7">材料仅保存在本地。最多 12 份、单份不超过 10 MiB；支持照片、TXT、MD、CSV、XLSX、DOCX、PDF。移除仅取消本次选中，不删除原件。</div>
    {previousAttachments.length > 0 && <details className="border-t border-stone-100 px-5 py-3 text-xs text-stone-500 sm:px-7"><summary className="cursor-pointer">复用已保存材料 · {previousAttachments.length} 份</summary><div className="mt-3 flex max-h-40 flex-wrap gap-2 overflow-y-auto">{previousAttachments.map(attachment => <button key={attachment.id} type="button" disabled={busy} onClick={() => onSelect(attachment)} className={`${secondaryButton} max-w-full`}><Paperclip className="h-3 w-3 shrink-0" /><span className="truncate">{attachment.name}</span></button>)}</div></details>}
    {!editing && <div className="flex flex-wrap gap-x-4 gap-y-2 border-t border-stone-100 px-5 py-4 sm:px-7"><span className="text-[10px] leading-6 text-stone-400">试试这样说</span>{examples.map(example => <button key={example} type="button" disabled={busy} onClick={() => setBrief(example)} className="text-left text-[11px] leading-6 text-emerald-800 underline decoration-emerald-200 underline-offset-4 hover:decoration-emerald-600">{example}</button>)}</div>}
  </section>
}
