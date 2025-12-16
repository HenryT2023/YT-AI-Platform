'use client'

import Link from 'next/link'
import { MessageCircle, Sparkles, Activity, Loader2 } from 'lucide-react'
import { useState, useEffect } from 'react'
import { fetchPublicNPCs, type PublicNPC } from '@/lib/api'

// 默认 NPC 列表（fallback）
const DEFAULT_NPC_LIST = [
  {
    npc_id: 'npc_elder_chen',
    name: '陈老伯',
    role: '村中长者',
    intro: '严田村的老一辈，见证了村庄的变迁，熟知各种传统习俗和历史故事。',
    avatar_emoji: '👴',
    color: 'from-amber-500 to-orange-600',
  },
]

interface NPCCardData {
  id: string
  name: string
  title: string
  description: string
  avatar: string
  color: string
}

function transformNPC(npc: PublicNPC): NPCCardData {
  return {
    id: npc.npc_id,
    name: npc.name,
    title: npc.role || '村民',
    description: npc.intro || '',
    avatar: npc.avatar_emoji || '👤',
    color: npc.color || 'from-slate-500 to-slate-600',
  }
}

function NPCCard({ npc }: { npc: NPCCardData }) {
  return (
    <Link href={`/npc/${npc.id}`} className="block">
      <div className="relative overflow-hidden rounded-2xl bg-white dark:bg-slate-800 shadow-lg hover:shadow-xl transition-all duration-300 active:scale-[0.98]">
        {/* 渐变背景 */}
        <div className={`absolute inset-0 bg-gradient-to-br ${npc.color} opacity-10`} />
        
        <div className="relative p-5">
          {/* 头像和基本信息 */}
          <div className="flex items-start gap-4">
            <div className={`flex-shrink-0 w-16 h-16 rounded-xl bg-gradient-to-br ${npc.color} flex items-center justify-center text-3xl shadow-md`}>
              {npc.avatar}
            </div>
            
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
                {npc.name}
              </h3>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
                {npc.title}
              </p>
            </div>
            
            <div className={`flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br ${npc.color} flex items-center justify-center`}>
              <MessageCircle className="w-5 h-5 text-white" />
            </div>
          </div>
          
          {/* 描述 */}
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300 line-clamp-2">
            {npc.description}
          </p>
          
          {/* 底部提示 */}
          <div className="mt-4 flex items-center justify-end text-xs text-slate-400 dark:text-slate-500">
            <Sparkles className="w-3.5 h-3.5 mr-1" />
            点击开始对话
          </div>
        </div>
      </div>
    </Link>
  )
}

export default function HomePage() {
  const [npcs, setNpcs] = useState<NPCCardData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadNPCs() {
      setLoading(true)
      setError(null)
      
      try {
        const data = await fetchPublicNPCs()
        if (data.length > 0) {
          setNpcs(data.map(transformNPC))
        } else {
          // Fallback to default
          setNpcs(DEFAULT_NPC_LIST.map(npc => ({
            id: npc.npc_id,
            name: npc.name,
            title: npc.role || '村民',
            description: npc.intro || '',
            avatar: npc.avatar_emoji || '👤',
            color: npc.color || 'from-slate-500 to-slate-600',
          })))
        }
      } catch (err) {
        console.error('Failed to load NPCs:', err)
        setError('加载失败，请刷新重试')
        // Fallback
        setNpcs(DEFAULT_NPC_LIST.map(npc => ({
          id: npc.npc_id,
          name: npc.name,
          title: npc.role || '村民',
          description: npc.intro || '',
          avatar: npc.avatar_emoji || '👤',
          color: npc.color || 'from-slate-500 to-slate-600',
        })))
      } finally {
        setLoading(false)
      }
    }
    
    loadNPCs()
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-lg border-b border-slate-200 dark:border-slate-700">
        <div className="px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">
              🌾 严田 AI
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
              选择一位村民，开始你的故事
            </p>
          </div>
          <Link
            href="/health"
            className="p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="系统状态"
          >
            <Activity className="w-5 h-5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300" />
          </Link>
        </div>
      </header>
      
      {/* NPC 列表 */}
      <div className="px-4 py-6 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
          </div>
        ) : error ? (
          <div className="text-center py-12 text-slate-500">
            {error}
          </div>
        ) : npcs.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            暂无可用的 NPC
          </div>
        ) : (
          npcs.map((npc) => (
            <NPCCard key={npc.id} npc={npc} />
          ))
        )}
      </div>
      
      {/* Footer */}
      <footer className="px-4 py-8 text-center">
        <p className="text-xs text-slate-400 dark:text-slate-500">
          严田 AI 文明引擎 · 让乡村故事永续流传
        </p>
      </footer>
    </div>
  )
}
