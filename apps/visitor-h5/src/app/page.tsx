'use client'

import Link from 'next/link'
import { MessageCircle, Sparkles, Activity, Loader2, Target, Sun, Leaf, Award, ChevronRight } from 'lucide-react'
import { useState, useEffect } from 'react'
import { fetchPublicNPCs, type PublicNPC } from '@/lib/api'

interface HomeRecommendations {
  solar_term: {
    name: string
    description: string
    farming_advice: string
    poem: string
    customs: string[]
    foods: string[]
  }
  recommended_quests: Array<{
    id: string
    title: string
    description: string
    difficulty: string
    reason: string
  }>
  achievement_hints: Array<{
    name: string
    progress: string
    hint: string
  }>
  topics: string[]
  greeting: string
}

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
  const [recommendations, setRecommendations] = useState<HomeRecommendations | null>(null)

  useEffect(() => {
    async function loadData() {
      setLoading(true)
      setError(null)
      
      try {
        // 并行加载 NPC 和推荐数据
        const [npcData, recData] = await Promise.all([
          fetchPublicNPCs(),
          fetch('/api/recommendations/home').then(r => r.ok ? r.json() : null).catch(() => null),
        ])

        if (npcData.length > 0) {
          setNpcs(npcData.map(transformNPC))
        } else {
          setNpcs(DEFAULT_NPC_LIST.map(npc => ({
            id: npc.npc_id,
            name: npc.name,
            title: npc.role || '村民',
            description: npc.intro || '',
            avatar: npc.avatar_emoji || '👤',
            color: npc.color || 'from-slate-500 to-slate-600',
          })))
        }

        if (recData) {
          setRecommendations(recData)
        }
      } catch (err) {
        console.error('Failed to load data:', err)
        setError('加载失败，请刷新重试')
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
    
    loadData()
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
          <div className="flex items-center gap-2">
            <Link
              href="/quests"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-to-r from-indigo-500 to-purple-600 text-white text-sm font-medium hover:shadow-lg transition-all active:scale-[0.98]"
            >
              <Target className="w-4 h-4" />
              任务
            </Link>
            <Link
              href="/health"
              className="p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              title="系统状态"
            >
              <Activity className="w-5 h-5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300" />
            </Link>
          </div>
        </div>
      </header>
      
      {/* 个性化问候 */}
      {recommendations?.greeting && (
        <div className="px-4 pt-4">
          <div className="bg-gradient-to-r from-green-500 to-emerald-600 rounded-2xl p-4 text-white">
            <p className="text-lg font-medium">{recommendations.greeting}</p>
          </div>
        </div>
      )}

      {/* 今日节气 */}
      {recommendations?.solar_term?.name && (
        <div className="px-4 pt-4">
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <Sun className="w-5 h-5 text-orange-500" />
              <h2 className="font-semibold text-slate-900 dark:text-white">今日节气</h2>
              <span className="px-2 py-0.5 bg-orange-100 text-orange-700 rounded-full text-sm font-medium">
                {recommendations.solar_term.name}
              </span>
            </div>
            {recommendations.solar_term.description && (
              <p className="text-sm text-slate-600 dark:text-slate-300 mb-2">
                {recommendations.solar_term.description}
              </p>
            )}
            {recommendations.solar_term.poem && (
              <p className="text-sm text-slate-500 dark:text-slate-400 italic border-l-2 border-orange-300 pl-3">
                "{recommendations.solar_term.poem}"
              </p>
            )}
            {recommendations.solar_term.customs?.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {recommendations.solar_term.customs.map((custom, i) => (
                  <span key={i} className="px-2 py-1 bg-slate-100 dark:bg-slate-700 rounded text-xs text-slate-600 dark:text-slate-300">
                    {custom}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 推荐话题 */}
      {recommendations?.topics && recommendations.topics.length > 0 && (
        <div className="px-4 pt-4">
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <Leaf className="w-5 h-5 text-green-500" />
              <h2 className="font-semibold text-slate-900 dark:text-white">推荐话题</h2>
            </div>
            <div className="flex flex-wrap gap-2">
              {recommendations.topics.map((topic, i) => (
                <span key={i} className="px-3 py-1.5 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full text-sm">
                  {topic}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 成就提示 */}
      {recommendations?.achievement_hints && recommendations.achievement_hints.length > 0 && (
        <div className="px-4 pt-4">
          <div className="bg-white dark:bg-slate-800 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-3">
              <Award className="w-5 h-5 text-purple-500" />
              <h2 className="font-semibold text-slate-900 dark:text-white">即将解锁</h2>
            </div>
            <div className="space-y-2">
              {recommendations.achievement_hints.map((hint, i) => (
                <div key={i} className="flex items-center justify-between p-2 bg-purple-50 dark:bg-purple-900/20 rounded-lg">
                  <div>
                    <p className="text-sm font-medium text-slate-900 dark:text-white">{hint.name}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">{hint.hint}</p>
                  </div>
                  <span className="text-sm font-medium text-purple-600 dark:text-purple-400">{hint.progress}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* NPC 列表 */}
      <div className="px-4 py-4">
        <div className="flex items-center gap-2 mb-3">
          <MessageCircle className="w-5 h-5 text-blue-500" />
          <h2 className="font-semibold text-slate-900 dark:text-white">与村民对话</h2>
        </div>
        <div className="space-y-4">
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
