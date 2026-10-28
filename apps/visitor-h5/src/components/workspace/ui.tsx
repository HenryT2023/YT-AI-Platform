import { ReactNode } from 'react'

export function Tag({ children, amber = false }: { children: ReactNode; amber?: boolean }) {
  return <span className={`inline-flex max-w-full items-center rounded-md px-2 py-1 text-[10px] leading-4 ${amber ? 'bg-amber-50 text-amber-800' : 'bg-stone-100 text-stone-500'}`}>{children}</span>
}
export function Section({ number, title, note, children }: { number: string; title: string; note?: string; children: ReactNode }) {
  return <section className="min-w-0 border-t border-stone-200/80 py-6 first:border-t-0"><div className="mb-4 flex items-baseline gap-3"><span className="font-serif text-sm text-emerald-700/60">{number}</span><div><h3 className="text-sm font-semibold text-stone-800">{title}</h3>{note && <p className="mt-1 text-[11px] leading-5 text-stone-400">{note}</p>}</div></div>{children}</section>
}
export const primaryButton = 'inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-emerald-950 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-800 disabled:cursor-not-allowed disabled:opacity-40'
export const secondaryButton = 'inline-flex items-center justify-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-medium text-stone-600 transition hover:border-emerald-400 hover:text-emerald-900 disabled:cursor-not-allowed disabled:opacity-40'
