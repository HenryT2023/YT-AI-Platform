'use client'

import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Target, Clock, Star, CheckCircle2, Loader2, Send, AlertCircle } from 'lucide-react'
import { useState, useEffect } from 'react'
import { 
  fetchPublicQuests, 
  fetchQuestProgress, 
  submitQuest, 
  isQuestSubmitError,
  type PublicQuest,
  type QuestSubmissionItem,
} from '@/lib/api'
import { getOrCreateGlobalSessionId } from '@/lib/session'

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

// Toast 组件
function Toast({ message, type, onClose }: { message: string; type: 'success' | 'error'; onClose: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onClose, 3000)
    return () => clearTimeout(timer)
  }, [onClose])

  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 animate-in fade-in slide-in-from-top-2 duration-300">
      <div className={`flex items-center gap-2 px-4 py-3 rounded-xl shadow-lg ${
        type === 'success' 
          ? 'bg-green-500 text-white' 
          : 'bg-red-500 text-white'
      }`}>
        {type === 'success' ? (
          <CheckCircle2 className="w-5 h-5" />
        ) : (
          <AlertCircle className="w-5 h-5" />
        )}
        <span className="text-sm font-medium">{message}</span>
      </div>
    </div>
  )
}

export default function QuestDetailPage() {
  const params = useParams()
  const router = useRouter()
  const questId = params.quest_id as string

  const [quest, setQuest] = useState<PublicQuest | null>(null)
  const [submissions, setSubmissions] = useState<QuestSubmissionItem[]>([])
  const [isCompleted, setIsCompleted] = useState(false)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [answer, setAnswer] = useState('')
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  // v0.2.2 审核状态
  const [latestReviewStatus, setLatestReviewStatus] = useState<'pending' | 'approved' | 'rejected' | null>(null)
  const [latestReviewComment, setLatestReviewComment] = useState<string | null>(null)

  useEffect(() => {
    async function loadQuestDetail() {
      setLoading(true)
      
      try {
        const sessionId = getOrCreateGlobalSessionId()
        
        // 并行加载任务列表和进度
        const [questsData, progressData] = await Promise.all([
          fetchPublicQuests(),
          fetchQuestProgress(sessionId),
        ])
        
        // 找到当前任务
        const currentQuest = questsData.find(q => q.quest_id === questId)
        if (currentQuest) {
          setQuest(currentQuest)
        }
        
        // 设置进度
        setIsCompleted(progressData.completed_quest_ids.includes(questId))
        const questSubmissions = progressData.submissions.filter(s => s.quest_id === questId)
        setSubmissions(questSubmissions)
        
        // v0.2.2: 获取最新审核状态
        if (questSubmissions.length > 0) {
          const latest = questSubmissions[0] // 已按 created_at desc 排序
          setLatestReviewStatus(latest.review_status)
          setLatestReviewComment(latest.review_comment || null)
        }
      } catch (err) {
        console.error('Failed to load quest detail:', err)
      } finally {
        setLoading(false)
      }
    }
    
    loadQuestDetail()
  }, [questId])

  const handleSubmit = async () => {
    if (!answer.trim() || submitting) return
    
    setSubmitting(true)
    
    try {
      const sessionId = getOrCreateGlobalSessionId()
      
      const result = await submitQuest(questId, {
        session_id: sessionId,
        proof_type: 'text',
        proof_payload: { answer: answer.trim() },
      })
      
      if (isQuestSubmitError(result)) {
        setToast({ message: result.message, type: 'error' })
      } else {
        setToast({ message: '提交成功！', type: 'success' })
        setAnswer('')
        
        // 刷新进度
        const progressData = await fetchQuestProgress(sessionId)
        setIsCompleted(progressData.completed_quest_ids.includes(questId))
        const questSubmissions = progressData.submissions.filter(s => s.quest_id === questId)
        setSubmissions(questSubmissions)
        
        // v0.2.2: 更新审核状态
        if (questSubmissions.length > 0) {
          const latest = questSubmissions[0]
          setLatestReviewStatus(latest.review_status)
          setLatestReviewComment(latest.review_comment || null)
        }
      }
    } catch (err) {
      console.error('Submit failed:', err)
      setToast({ message: '提交失败，请重试', type: 'error' })
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    )
  }

  if (!quest) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
        <header className="sticky top-0 z-10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-lg border-b border-slate-200 dark:border-slate-700">
          <div className="px-4 py-4 flex items-center gap-3">
            <Link
              href="/quests"
              className="p-2 -ml-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <ArrowLeft className="w-5 h-5 text-slate-600 dark:text-slate-400" />
            </Link>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">任务详情</h1>
          </div>
        </header>
        <div className="flex items-center justify-center py-20">
          <p className="text-slate-500">任务不存在</p>
        </div>
      </div>
    )
  }

  const rewardPoints = quest.rewards?.points as number | undefined
  const hasSubmission = submissions.length > 0

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800">
      {/* Toast */}
      {toast && (
        <Toast 
          message={toast.message} 
          type={toast.type} 
          onClose={() => setToast(null)} 
        />
      )}

      {/* Header */}
      <header className="sticky top-0 z-10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-lg border-b border-slate-200 dark:border-slate-700">
        <div className="px-4 py-4 flex items-center gap-3">
          <Link
            href="/quests"
            className="p-2 -ml-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-slate-600 dark:text-slate-400" />
          </Link>
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold text-slate-900 dark:text-white truncate">
              {quest.display_name || quest.name}
            </h1>
          </div>
          {/* v0.2.2 审核状态标签 */}
          {latestReviewStatus === 'approved' && (
            <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-green-500 text-white text-xs font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              已完成
            </div>
          )}
          {latestReviewStatus === 'pending' && (
            <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-blue-500 text-white text-xs font-medium">
              审核中
            </div>
          )}
          {latestReviewStatus === 'rejected' && (
            <div className="flex items-center gap-1 px-2 py-1 rounded-full bg-orange-500 text-white text-xs font-medium">
              被驳回
            </div>
          )}
        </div>
      </header>

      {/* 任务信息 */}
      <div className="px-4 py-6">
        {/* 基本信息卡片 */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-lg p-5">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0 w-14 h-14 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <Target className="w-7 h-7 text-white" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 flex-wrap">
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
              {rewardPoints && (
                <div className="mt-2 flex items-center gap-1 text-sm text-amber-600 dark:text-amber-400">
                  <Star className="w-4 h-4 fill-current" />
                  <span className="font-medium">完成可获得 {rewardPoints} 积分</span>
                </div>
              )}
            </div>
          </div>
          
          {quest.description && (
            <p className="mt-4 text-slate-600 dark:text-slate-300">
              {quest.description}
            </p>
          )}
        </div>

        {/* 任务步骤 */}
        {quest.steps && quest.steps.length > 0 && (
          <div className="mt-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">
              任务步骤
            </h2>
            <div className="space-y-3">
              {quest.steps.map((step, index) => (
                <div 
                  key={step.step_number}
                  className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 w-7 h-7 rounded-full bg-indigo-100 dark:bg-indigo-900 flex items-center justify-center">
                      <span className="text-sm font-semibold text-indigo-600 dark:text-indigo-300">
                        {step.step_number}
                      </span>
                    </div>
                    <div className="flex-1">
                      <h3 className="font-medium text-slate-900 dark:text-white">
                        {step.name}
                      </h3>
                      {step.description && (
                        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                          {step.description}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 提交历史 */}
        {hasSubmission && (
          <div className="mt-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">
              提交记录
            </h2>
            <div className="space-y-3">
              {submissions.map((sub) => (
                <div 
                  key={sub.submission_id}
                  className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow"
                >
                  <div className="flex items-center justify-between">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                      sub.review_status === 'approved' 
                        ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
                        : sub.review_status === 'rejected'
                        ? 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300'
                        : 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300'
                    }`}>
                      {sub.review_status === 'approved' ? '已通过' : sub.review_status === 'rejected' ? '未通过' : '审核中'}
                    </span>
                    <span className="text-xs text-slate-400">
                      {new Date(sub.created_at).toLocaleString('zh-CN')}
                    </span>
                  </div>
                  {typeof sub.proof_payload?.answer === 'string' && sub.proof_payload.answer && (
                    <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                      {sub.proof_payload.answer}
                    </p>
                  )}
                  {/* v0.2.2: 显示驳回原因 */}
                  {sub.review_status === 'rejected' && sub.review_comment && (
                    <div className="mt-2 p-2 bg-red-50 dark:bg-red-900/20 rounded-lg">
                      <p className="text-xs text-red-600 dark:text-red-400">
                        <span className="font-medium">驳回原因：</span>{sub.review_comment}
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* v0.2.2 审核状态提示 */}
        {latestReviewStatus === 'approved' && (
          <div className="mt-6 bg-green-50 dark:bg-green-900/20 rounded-2xl p-4">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-8 h-8 text-green-500" />
              <div>
                <h3 className="font-semibold text-green-700 dark:text-green-300">任务已完成</h3>
                <p className="text-sm text-green-600 dark:text-green-400">恭喜你完成了这个任务！</p>
              </div>
            </div>
          </div>
        )}

        {latestReviewStatus === 'pending' && (
          <div className="mt-6 bg-blue-50 dark:bg-blue-900/20 rounded-2xl p-4">
            <div className="flex items-center gap-3">
              <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
              <div>
                <h3 className="font-semibold text-blue-700 dark:text-blue-300">等待审核</h3>
                <p className="text-sm text-blue-600 dark:text-blue-400">你的提交正在审核中，请耐心等待</p>
              </div>
            </div>
          </div>
        )}

        {/* 提交表单：未提交 或 被驳回时显示 */}
        {(latestReviewStatus === null || latestReviewStatus === 'rejected') && (
          <div className="mt-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-3">
              {latestReviewStatus === 'rejected' ? '重新提交' : '提交答案'}
            </h2>
            
            {/* 驳回提示 */}
            {latestReviewStatus === 'rejected' && latestReviewComment && (
              <div className="mb-4 bg-orange-50 dark:bg-orange-900/20 rounded-xl p-4">
                <div className="flex items-start gap-2">
                  <AlertCircle className="w-5 h-5 text-orange-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-orange-700 dark:text-orange-300">上次提交被驳回</p>
                    <p className="text-sm text-orange-600 dark:text-orange-400 mt-1">{latestReviewComment}</p>
                  </div>
                </div>
              </div>
            )}
            
            <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-lg p-4">
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                placeholder="请输入你的答案..."
                className="w-full h-32 px-4 py-3 bg-slate-50 dark:bg-slate-700 rounded-xl border-0 resize-none focus:ring-2 focus:ring-indigo-500 text-slate-900 dark:text-white placeholder-slate-400"
                maxLength={500}
              />
              <div className="flex items-center justify-between mt-3">
                <span className="text-xs text-slate-400">
                  {answer.length}/500
                </span>
                <button
                  onClick={handleSubmit}
                  disabled={!answer.trim() || submitting}
                  className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 text-white rounded-xl font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:shadow-lg transition-all active:scale-[0.98]"
                >
                  {submitting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  {latestReviewStatus === 'rejected' ? '重新提交' : '提交'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
