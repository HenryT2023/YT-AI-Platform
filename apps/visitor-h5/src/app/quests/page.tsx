'use client'

import Link from 'next/link'
import { ArrowLeft, Target, Clock, Star, CheckCircle2, Loader2 } from 'lucide-react'
import { useState, useEffect } from 'react'
import { fetchPublicQuests, fetchQuestProgress, type PublicQuest } from '@/lib/api'
import { getOrCreateGlobalSessionId } from '@/lib/session'

interface QuestCardData {
  quest_id: string
  name: string
  display_name?: string
  description?: string
  difficulty?: string
  estimated_duration_minutes?: number
  rewards: Record<string, unknown>
  isCompleted: boolean  // review_status === 'approved'
  hasSubmission: boolean
  // v0.2.2 审核状态
  reviewStatus?: 'pending' | 'approved' | 'rejected'
}

function getDifficultyColor(difficulty?: string): string {
  switch (difficulty) {
    case 'easy':
      return 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
    case 'medium':
      return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300'
    case 'hard':
      return 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300'
    default:
      return 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
  }
}

function getDifficultyLabel(difficulty?: string): string {
  switch (difficulty) {
    case 'easy':
      return '简单'
    case 'medium':
      return '中等'
    case 'hard':
      return '困难'
    default:
      return '未知'
  }
}

function QuestCard({ quest }: { quest: QuestCardData }) {
  const rewardPoints = quest.rewards?.points as number | undefined
  
  return (
    <Link href={`/quests/${quest.quest_id}`} className="block">
      <div className="relative overflow-hidden rounded-2xl bg-white dark:bg-slate-800 shadow-lg hover:shadow-xl transition-all duration-300 active:scale-[0.98]">
        {/* v0.2.2 审核状态标签 */}
        {quest.reviewStatus === 'approved' && (
          <div className="absolute top-3 right-3 z-10">
            <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-green-500 text-white text-xs font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              已完成
            </div>
          </div>
        )}
        
        {quest.reviewStatus === 'pending' && quest.hasSubmission && (
          <div className="absolute top-3 right-3 z-10">
            <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-blue-500 text-white text-xs font-medium">
              审核中
            </div>
          </div>
        )}
        
        {quest.reviewStatus === 'rejected' && (
          <div className="absolute top-3 right-3 z-10">
            <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-orange-500 text-white text-xs font-medium">
              被驳回
            </div>
          </div>
        )}
        
        <div className="p-5">
          {/* 标题和难度 */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white truncate">
                {quest.display_name || quest.name}
              </h3>
              <div className="flex items-center gap-2 mt-2">
                {quest.difficulty && (
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getDifficultyColor(quest.difficulty)}`}>
                    {getDifficultyLabel(quest.difficulty)}
                  </span>
                )}
                {quest.estimated_duration_minutes && (
                  <span className="flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                    <Clock className="w-3.5 h-3.5" />
                    {quest.estimated_duration_minutes} 分钟
                  </span>
                )}
              </div>
            </div>
            
            <div className="flex-shrink-0 w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <Target className="w-6 h-6 text-white" />
            </div>
          </div>
          
          {/* 描述 */}
          {quest.description && (
            <p className="mt-3 text-sm text-slate-600 dark:text-slate-300 line-clamp-2">
              {quest.description}
            </p>
          )}
          
          {/* 奖励 */}
          {rewardPoints && (
            <div className="mt-4 flex items-center gap-1 text-sm text-amber-600 dark:text-amber-400">
              <Star className="w-4 h-4 fill-current" />
              <span className="font-medium">{rewardPoints} 积分</span>
            </div>
          )}
        </div>
      </div>
    </Link>
  )
}

export default function QuestsPage() {
  const [quests, setQuests] = useState<QuestCardData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadQuests() {
      setLoading(true)
      setError(null)
      
      try {
        const sessionId = getOrCreateGlobalSessionId()
        
        // 并行加载任务列表和进度
        const [questsData, progressData] = await Promise.all([
          fetchPublicQuests(),
          fetchQuestProgress(sessionId),
        ])
        
        const completedSet = new Set(progressData.completed_quest_ids)
        const submittedSet = new Set(progressData.submissions.map(s => s.quest_id))
        
        // v0.2.2: 获取每个任务的最新审核状态
        const questReviewStatus = new Map<string, 'pending' | 'approved' | 'rejected'>()
        for (const sub of progressData.submissions) {
          // 取最新的提交状态（submissions 已按 created_at desc 排序）
          if (!questReviewStatus.has(sub.quest_id)) {
            questReviewStatus.set(sub.quest_id, sub.review_status)
          }
        }
        
        const questCards: QuestCardData[] = questsData.map(q => ({
          quest_id: q.quest_id,
          name: q.name,
          display_name: q.display_name,
          description: q.description,
          difficulty: q.difficulty,
          estimated_duration_minutes: q.estimated_duration_minutes,
          rewards: q.rewards,
          isCompleted: completedSet.has(q.quest_id),
          hasSubmission: submittedSet.has(q.quest_id),
          reviewStatus: questReviewStatus.get(q.quest_id),
        }))
        
        setQuests(questCards)
      } catch (err) {
        console.error('Failed to load quests:', err)
        setError('加载失败，请刷新重试')
      } finally {
        setLoading(false)
      }
    }
    
    loadQuests()
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-lg border-b border-slate-200 dark:border-slate-700">
        <div className="px-4 py-4 flex items-center gap-3">
          <Link
            href="/"
            className="p-2 -ml-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-slate-600 dark:text-slate-400" />
          </Link>
          <div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">
              🎯 研学任务
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
              完成任务，探索严田村
            </p>
          </div>
        </div>
      </header>
      
      {/* 任务列表 */}
      <div className="px-4 py-6 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
          </div>
        ) : error ? (
          <div className="text-center py-12 text-slate-500">
            {error}
          </div>
        ) : quests.length === 0 ? (
          <div className="text-center py-12 text-slate-500">
            暂无可用的任务
          </div>
        ) : (
          quests.map((quest) => (
            <QuestCard key={quest.quest_id} quest={quest} />
          ))
        )}
      </div>
      
      {/* Footer */}
      <footer className="px-4 py-8 text-center">
        <p className="text-xs text-slate-400 dark:text-slate-500">
          完成任务可获得积分奖励
        </p>
      </footer>
    </div>
  )
}
