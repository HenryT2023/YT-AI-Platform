'use client'
import { useEffect, useRef, useState } from 'react'
import { RenderJob, RenderState, VideoPackage } from './types'
import { Check, GROWTH_API, Notice, Panel, Pill, dateTime } from './ui'

const buttonClass = 'rounded-lg bg-emerald-800 px-4 py-2.5 text-xs font-medium text-white hover:bg-emerald-900 disabled:cursor-not-allowed disabled:opacity-40'
const linkClass = 'rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs text-emerald-800'
const jobNames: Record<RenderJob['status'], string> = { queued: '排队中', running: '正在生成', succeeded: '本地视频已生成', failed: '本次生成未完成' }
const phaseNames: Record<string, string> = { queued: '等待本地工作进程', preparing: '准备脚本、分镜与素材', validating: '核对版本与素材', rendering: '合成画面与字幕', encoding: '编码视频', verifying: '核对成片文件', finalizing: '保存成片与回执', completed: '完成', succeeded: '完成', failed: '失败' }

// Only server-returned local artifact routes may become media or download URLs.
function localRenderUrl(value?: string) {
  if (!value || !value.startsWith(`${GROWTH_API}/`) || typeof window === 'undefined') return undefined
  try {
    const parsed = new URL(value, window.location.origin)
    return parsed.origin === window.location.origin && parsed.pathname.startsWith(`${GROWTH_API}/`) ? `${parsed.pathname}${parsed.search}` : undefined
  } catch { return undefined }
}
function isPending(job: RenderJob) { return job.status === 'queued' || job.status === 'running' }
function errorMessage(body: { detail?: unknown }, status: number) {
  if (typeof body.detail === 'string') return body.detail
  if (Array.isArray(body.detail)) return body.detail.map(item => item && typeof item === 'object' && 'msg' in item ? String(item.msg) : '输入格式不正确').join('；')
  return `本地视频操作未完成（${status}），请刷新状态后重试。`
}

function RenderJobResult({ job, pkg, historical = false }: { job: RenderJob; pkg: VideoPackage; historical?: boolean }) {
  const [playbackError, setPlaybackError] = useState(false)
  const video = localRenderUrl(job.artifacts?.video)
  const download = localRenderUrl(job.artifacts?.download)
  const poster = localRenderUrl(job.artifacts?.poster)
  const receipt = localRenderUrl(job.artifacts?.receipt)
  const subtitles = localRenderUrl(job.artifacts?.subtitles)
  const oldVersion = job.stale || job.package_hash !== pkg.hash
  const progress = Number.isFinite(job.progress) ? Math.max(0, Math.min(100, job.progress)) : 0
  return <article className="space-y-4 rounded-xl border border-stone-200 bg-stone-50 p-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex flex-wrap gap-2"><Pill tone={job.status === 'succeeded' && !oldVersion ? 'green' : 'amber'}>{jobNames[job.status]}</Pill><Pill>本地待审版 · 未发布</Pill>{oldVersion && <Pill tone="amber">历史输出 · 当前版本不可沿用</Pill>}{historical && !oldVersion && <Pill>较早制作记录</Pill>}</div><span className="text-[10px] text-stone-400">第 {job.attempt} 次 · {dateTime(job.created_at)}</span></div>
    <p className="break-all text-[10px] leading-5 text-stone-500">成片对应指纹：{job.package_hash}<br />制作器：{job.renderer_version}</p>
    {oldVersion && <Notice>这份输出保留原来的脚本与素材依据，不能代表当前版本。{job.stale_reasons.length ? ` ${job.stale_reasons.join('；')}` : '修改后需重新保存、确认并生成。'}</Notice>}
    {isPending(job) && <div role="status" aria-live="polite"><div className="mb-2 flex justify-between gap-3 text-xs text-stone-600"><span>{phaseNames[job.phase] || '正在处理本地制作任务'}</span><span>{Math.round(progress)}%</span></div><progress value={progress} max={100} aria-label="本地视频生成进度" className="h-2 w-full overflow-hidden rounded-full accent-emerald-800" /><p className="mt-2 text-[11px] leading-6 text-stone-500">可以离开页面，返回后会恢复任务状态。此进度由本地制作任务回报。</p></div>}
    {job.status === 'failed' && <p role="alert" className="rounded-lg bg-red-50 p-3 text-xs leading-6 text-red-800">{job.error?.message || '本地任务未完成。可核对素材与版本后重试。'}{job.error?.code && <span className="mt-1 block text-[10px]">原因代码：{job.error.code}</span>}</p>}
    {job.status === 'succeeded' && <>
      {video ? <div className="mx-auto max-w-[310px]"><video key={video} controls playsInline preload="metadata" poster={poster} src={video} onError={() => setPlaybackError(true)} className="aspect-[9/16] w-full rounded-xl bg-stone-900">当前浏览器无法播放此视频，可下载 MP4 查看。</video></div> : <p className="text-xs leading-6 text-amber-800">未取得有效的本地预览地址，请刷新状态核对文件。</p>}
      {playbackError && <p role="alert" className="text-xs leading-6 text-amber-800">浏览器未能读取视频。请刷新状态，或下载 MP4 在本机播放器查看。</p>}
      {job.metadata && <p className="text-center text-[11px] text-stone-500">{job.metadata.width} × {job.metadata.height} · {job.metadata.duration_seconds} 秒 · 原创配乐与字幕，无口播</p>}
      <div className="flex flex-wrap justify-center gap-2">{download && <a href={download} download className={buttonClass}>下载 MP4</a>}{poster && <a href={poster} download className={linkClass}>下载封面</a>}{receipt && <a href={receipt} download className={linkClass}>下载制作回执</a>}{subtitles && <a href={subtitles} download className={linkClass}>下载字幕</a>}</div>
      <p className="text-[11px] leading-6 text-stone-500">历史照片、设计示意与待拍画面保留标识。此文件用于本地预览，发布前另行核对事实、产品交付与素材使用权。</p>
    </>}
  </article>
}

export default function RenderPanel({ pkg, dirty }: { pkg: VideoPackage; dirty: boolean }) {
  const [state, setState] = useState<RenderState | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [checked, setChecked] = useState(false)
  const [error, setError] = useState('')
  const [readError, setReadError] = useState('')
  const [message, setMessage] = useState('')
  const reload = useRef<() => void>(() => {})
  const mutation = useRef<AbortController | null>(null)
  const mutationLock = useRef(false)
  const mounted = useRef(false)

  useEffect(() => {
    let live = true
    let controller: AbortController | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    mounted.current = true
    setState(null); setLoading(true); setChecked(false); setError(''); setReadError(''); setMessage('')
    const clearTimer = () => { if (timer) clearTimeout(timer); timer = undefined }
    const readState = async () => {
      clearTimer()
      if (!live || document.hidden) return
      controller?.abort()
      const request = new AbortController()
      controller = request
      try {
        const response = await fetch(`${GROWTH_API}/packages/${encodeURIComponent(pkg.id)}/render-state`, { cache: 'no-store', signal: request.signal })
        const body = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(errorMessage(body, response.status))
        if (!live || request.signal.aborted) return
        const next = body as RenderState
        setState(next); setReadError('')
        if (next.jobs.some(isPending)) timer = setTimeout(readState, 2500)
      } catch (cause) {
        if (live && !request.signal.aborted) setReadError(cause instanceof Error ? cause.message : '未能读取本地视频状态。请刷新重试。')
      } finally { if (live && !request.signal.aborted) setLoading(false) }
    }
    reload.current = readState
    const visibilityChanged = () => { if (document.hidden) { clearTimer(); controller?.abort() } else void readState() }
    document.addEventListener('visibilitychange', visibilityChanged)
    void readState()
    return () => { live = false; mounted.current = false; clearTimer(); controller?.abort(); mutation.current?.abort(); document.removeEventListener('visibilitychange', visibilityChanged); reload.current = () => {} }
  }, [pkg.id, pkg.hash])

  async function post(path: string, payload: unknown, success: string) {
    if (mutationLock.current) return
    mutationLock.current = true; setBusy(true); setError(''); setMessage('')
    const request = new AbortController()
    mutation.current = request
    try {
      const response = await fetch(`${GROWTH_API}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Yantian-Local': '1' }, body: JSON.stringify(payload), signal: request.signal })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(errorMessage(body, response.status))
      if (mounted.current && !request.signal.aborted) { setMessage(success); setChecked(false); reload.current() }
    } catch (cause) {
      if (mounted.current && !request.signal.aborted) { setError(cause instanceof Error ? cause.message : '操作未完成，请刷新状态后重试。'); reload.current() }
    } finally { mutationLock.current = false; if (mounted.current && !request.signal.aborted) setBusy(false) }
  }

  const confirmation = state?.confirmation
  const valid = confirmation?.valid === true && confirmation.package_hash === pkg.hash
  const jobs = state ? [...state.jobs].sort((a, b) => (a.created_at || '').localeCompare(b.created_at || '') || a.attempt - b.attempt) : []
  const currentJobs = jobs.filter(job => job.package_hash === pkg.hash && !job.stale)
  const currentJob = currentJobs[currentJobs.length - 1]
  const pending = jobs.some(isPending)
  const historyJobs = jobs.filter(job => job.id !== currentJob?.id).reverse()
  const blocked = state?.readiness.blockers || []
  const warnings = state?.readiness.warnings || []
  const canGenerate = Boolean(state?.readiness.available && state.capabilities.available && valid && !dirty && !busy && !pending && !loading)
  const confirmationPayload = { package_hash: pkg.hash, confirmations: { script: true, storyboard: true, reference_labels: true }, note: '已在第二层核对本次脚本、分镜与参考标识，仅确认用于本地视频预览。' }

  return <Panel title="确认脚本与分镜，生成本地视频" note="仅在本机制作 1080 × 1920 竖版视频，配字幕与原创配乐。生成完成后可直接预览、下载；不自动发布。" action={<Pill>资料 v{pkg.version || 1}</Pill>}>
    <div className="space-y-5">
      <div className="rounded-xl bg-stone-50 p-4"><p className="text-xs font-medium text-stone-700">① 已保存版本</p><p className="mt-2 break-all text-[10px] leading-5 text-stone-500">资料 v{pkg.version || 1} · {pkg.hash}</p>{dirty && <p role="status" className="mt-3 text-xs leading-6 text-amber-800">上方有未保存修改。请先保存新版本，再确认和生成；下方已有视频仍对应原版本。</p>}</div>
      {loading && !state && <p role="status" className="text-xs text-stone-500">正在读取本地制作状态…</p>}
      {(error || readError) && <div role="alert" className="rounded-xl bg-red-50 p-4 text-xs leading-6 text-red-800">{error || readError}<button type="button" disabled={busy} onClick={() => reload.current()} className="ml-2 underline disabled:opacity-40">刷新制作状态</button></div>}
      {message && <p role="status" className="text-xs leading-6 text-emerald-800">{message}</p>}
      {state && <>
        {!state.capabilities.available && <Notice>本地制作环境尚未就绪：{state.capabilities.missing.length ? state.capabilities.missing.join('；') : '请核对本地制作依赖。'} 不会调用外部服务补做。</Notice>}
        {blocked.length > 0 && <div className="rounded-xl bg-amber-50 p-4 text-xs leading-6 text-amber-900"><p className="font-medium">生成前需处理</p><ul className="mt-2 list-disc space-y-1 pl-4">{blocked.map((item, index) => <li key={index}>{item}</li>)}</ul></div>}
        {warnings.length > 0 && <details className="rounded-xl border border-stone-200 p-4 text-xs leading-6 text-stone-600" open><summary className="cursor-pointer font-medium">本次画面与参考标识</summary><ul className="mt-2 list-disc space-y-1 pl-4">{warnings.map((item, index) => <li key={index}>{item}</li>)}</ul></details>}
        <div className="space-y-3 rounded-xl border border-stone-200 p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-xs font-medium">② 确认此版本用于本地制作</h3><Pill tone={valid ? 'green' : 'amber'}>{valid ? '此指纹已确认' : '待独立确认'}</Pill></div>
          {valid ? <p className="text-xs leading-6 text-stone-600">已确认资料 v{pkg.version || 1} 的脚本、分镜与参考标识。{confirmation?.created_at && <span className="block text-[10px] text-stone-400">{dateTime(confirmation.created_at)} · 本地人工声明</span>}</p> : <><Check checked={checked} onChange={setChecked}>我已复核上方已保存版本的脚本、分镜与历史 / 示意 / 待拍标识，确认用于本地视频预览。</Check>{confirmation && !confirmation.valid && <p className="text-[11px] leading-6 text-amber-800">原制作确认已失效。{confirmation.blockers.join('；')}</p>}<button type="button" disabled={busy || dirty || !checked || loading || pending} onClick={() => post(`/packages/${encodeURIComponent(pkg.id)}/render-confirmations`, confirmationPayload, '此精确版本已确认用于本地制作，尚未开始生成视频。')} className={buttonClass}>{busy ? '正在保存确认…' : '确认本次脚本与分镜'}</button></>}
          <p className="text-[11px] leading-6 text-stone-500">此确认仅采纳本次制作方向；核房、报价、素材使用权与发布审阅仍分别核对。这里不会自动勾选发布审核。</p>
        </div>
        <div className="space-y-4"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-xs font-medium">③ 手动生成视频</h3><button type="button" disabled={busy} onClick={() => reload.current()} className="text-xs text-emerald-800 underline disabled:opacity-40">刷新制作状态</button></div>
          {currentJob?.status === 'failed' ? <button type="button" disabled={!canGenerate} onClick={() => post(`/renders/${encodeURIComponent(currentJob.id)}/retry`, { package_hash: pkg.hash, confirmation_id: confirmation?.id }, '已提交本地重试任务，可在这里查看状态。')} className={buttonClass}>{busy ? '正在提交…' : '重试生成本地视频'}</button> : <button type="button" disabled={!canGenerate || currentJob?.status === 'succeeded'} onClick={() => post(`/packages/${encodeURIComponent(pkg.id)}/renders`, { package_hash: pkg.hash, confirmation_id: confirmation?.id }, '本地视频任务已提交，页面会自动更新进度。')} className={buttonClass}>{busy ? '正在提交…' : pending ? '本地视频正在生成…' : currentJob?.status === 'succeeded' ? '此版本已生成视频' : '生成本地视频'}</button>}
          {!valid && <p className="text-[11px] leading-6 text-stone-500">请先确认已保存的脚本与分镜，再手动开始生成。</p>}
          {currentJob && <RenderJobResult key={currentJob.id} job={currentJob} pkg={pkg} />}
          {historyJobs.length > 0 && <details className="rounded-xl border border-stone-200 p-4"><summary className="cursor-pointer text-xs font-medium text-stone-600">历史制作记录 · {historyJobs.length} 项</summary><div className="mt-4 space-y-4">{historyJobs.map(job => <RenderJobResult key={job.id} job={job} pkg={pkg} historical />)}</div></details>}
        </div>
      </>}
    </div>
  </Panel>
}
