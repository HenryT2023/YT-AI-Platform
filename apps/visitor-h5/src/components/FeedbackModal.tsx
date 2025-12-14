'use client'

import { useState } from 'react'
import { X, AlertTriangle, Loader2, CheckCircle } from 'lucide-react'
import { submitFeedback, isFeedbackError, type FeedbackType, type FeedbackSeverity } from '@/lib/api'
import { TENANT_ID, SITE_ID } from '@/lib/config'

interface FeedbackModalProps {
  isOpen: boolean
  onClose: () => void
  traceId: string
  originalResponse: string
  onSuccess: () => void
}

const FEEDBACK_TYPES: { value: FeedbackType; label: string; description: string }[] = [
  { value: 'fact_error', label: '事实不准确', description: '回答中的信息与事实不符' },
  { value: 'unsafe', label: '不当/不适合', description: '内容不恰当或有安全问题' },
  { value: 'other', label: '其他问题', description: '其他类型的问题' },
]

const SEVERITY_LEVELS: { value: FeedbackSeverity; label: string; color: string }[] = [
  { value: 'low', label: '轻微', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300' },
  { value: 'medium', label: '中等', color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300' },
  { value: 'high', label: '严重', color: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300' },
]

export default function FeedbackModal({
  isOpen,
  onClose,
  traceId,
  originalResponse,
  onSuccess,
}: FeedbackModalProps) {
  const [feedbackType, setFeedbackType] = useState<FeedbackType>('fact_error')
  const [severity, setSeverity] = useState<FeedbackSeverity>('medium')
  const [comment, setComment] = useState('')
  const [suggestedFix, setSuggestedFix] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  if (!isOpen) return null

  const handleSubmit = async () => {
    if (!comment.trim()) {
      setError('请填写问题描述')
      return
    }

    setIsSubmitting(true)
    setError(null)

    const result = await submitFeedback({
      tenant_id: TENANT_ID,
      site_id: SITE_ID,
      trace_id: traceId,
      feedback_type: feedbackType,
      severity,
      content: comment.trim(),
      suggested_fix: suggestedFix.trim() || undefined,
    })

    setIsSubmitting(false)

    if (isFeedbackError(result)) {
      setError(result.message)
    } else {
      setSuccess(true)
      setTimeout(() => {
        onSuccess()
        onClose()
        setFeedbackType('fact_error')
        setSeverity('medium')
        setComment('')
        setSuggestedFix('')
        setSuccess(false)
      }, 1500)
    }
  }

  const handleClose = () => {
    if (!isSubmitting) {
      onClose()
      setError(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50">
      <div className="fixed inset-0 bg-black/50" onClick={handleClose} />
      
      <div className="fixed bottom-0 left-0 right-0 bg-white dark:bg-slate-800 rounded-t-2xl shadow-xl max-h-[85vh] overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
            <h2 className="font-semibold text-slate-900 dark:text-white">纠错反馈</h2>
          </div>
          <button
            onClick={handleClose}
            disabled={isSubmitting}
            className="p-1.5 rounded-full hover:bg-slate-100 dark:hover:bg-slate-700"
          >
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        <div className="p-4 overflow-y-auto max-h-[calc(85vh-120px)]">
          {success ? (
            <div className="flex flex-col items-center justify-center py-8">
              <CheckCircle className="w-16 h-16 text-green-500 mb-4" />
              <p className="text-lg font-medium text-slate-900 dark:text-white">已提交，感谢你的纠错</p>
              <p className="text-sm text-slate-500 mt-1">我们会尽快处理</p>
            </div>
          ) : (
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  错误类型
                </label>
                <div className="space-y-2">
                  {FEEDBACK_TYPES.map((type) => (
                    <button
                      key={type.value}
                      onClick={() => setFeedbackType(type.value)}
                      className={`w-full text-left px-3 py-2.5 rounded-lg border transition-colors ${
                        feedbackType === type.value
                          ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                          : 'border-slate-200 dark:border-slate-600'
                      }`}
                    >
                      <div className="font-medium text-sm text-slate-900 dark:text-white">{type.label}</div>
                      <div className="text-xs text-slate-500">{type.description}</div>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  严重程度
                </label>
                <div className="flex gap-2">
                  {SEVERITY_LEVELS.map((level) => (
                    <button
                      key={level.value}
                      onClick={() => setSeverity(level.value)}
                      className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                        severity === level.value
                          ? level.color
                          : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
                      }`}
                    >
                      {level.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  问题描述 <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="请描述具体问题..."
                  rows={3}
                  className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">
                  建议修正（可选）
                </label>
                <textarea
                  value={suggestedFix}
                  onChange={(e) => setSuggestedFix(e.target.value)}
                  placeholder="如果知道正确答案，请填写..."
                  rows={2}
                  className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>

              {error && (
                <div className="px-3 py-2 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                  <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
                </div>
              )}
            </div>
          )}
        </div>

        {!success && (
          <div className="px-4 py-3 border-t border-slate-200 dark:border-slate-700 safe-area-inset-bottom">
            <button
              onClick={handleSubmit}
              disabled={isSubmitting || !comment.trim()}
              className={`w-full py-2.5 rounded-lg font-medium text-sm flex items-center justify-center gap-2 transition-colors ${
                isSubmitting || !comment.trim()
                  ? 'bg-slate-200 dark:bg-slate-700 text-slate-400 cursor-not-allowed'
                  : 'bg-primary-500 text-white hover:bg-primary-600'
              }`}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  提交中...
                </>
              ) : (
                '提交纠错'
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
