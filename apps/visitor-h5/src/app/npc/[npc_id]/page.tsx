'use client'

import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Send, Loader2, RotateCcw, ChevronDown, ChevronUp, BookOpen, Hash, Flag } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'
import { getOrCreateSessionId, clearSessionId } from '@/lib/session'
import { npcChat, isNPCChatError, getPolicyModeLabel, getPolicyModeColor, fetchPublicNPCs, type PolicyMode, type CitationItem, type PublicNPC } from '@/lib/api'
import FeedbackModal from '@/components/FeedbackModal'
import { LOCAL_OS_MODE } from '@/lib/config'

// NPC 数据缓存
let npcDataCache: Record<string, {
  name: string
  title: string
  avatar: string
  color: string
  greeting: string
}> | null = null

// 默认 NPC 数据（fallback）
const DEFAULT_NPC_DATA: Record<string, {
  name: string
  title: string
  avatar: string
  color: string
  greeting: string
}> = {
  npc_elder_chen: {
    name: '文化查证向导',
    title: '演示角色 · 非真实村民',
    avatar: '👴',
    color: 'from-amber-500 to-orange-600',
    greeting: '你好，这是原严田 OS 的演示对话角色，不代表真实村民或个人经历。你可以查问本地知识；有依据时显示出处，资料不足时明确说明。',
  },
  npc_xiaomei: {
    name: '乡村探索向导',
    title: '演示角色 · 非真实村民',
    avatar: '👩',
    color: 'from-pink-500 to-rose-600',
    greeting: '这是乡村探索的演示角色，不代表真实返乡者或经营项目。请用问题查证资料，未核验的内容不会补写成村庄故事。',
  },
  npc_master_li: {
    name: '工艺学习向导',
    title: '演示角色 · 无传承人身份认定',
    avatar: '👨‍🔧',
    color: 'from-emerald-500 to-teal-600',
    greeting: '这是工艺学习的演示角色，不代表真实工艺师或非遗传承人。图样与解释需要来源，制作意见需要实际审阅。',
  },
}

// 从 API 加载 NPC 数据
async function loadNPCData(): Promise<Record<string, { name: string; title: string; avatar: string; color: string; greeting: string }>> {
  if (npcDataCache) return npcDataCache
  
  try {
    const npcs = await fetchPublicNPCs()
    if (npcs.length > 0) {
      npcDataCache = {}
      for (const npc of npcs) {
        npcDataCache[npc.npc_id] = {
          name: npc.name,
          title: LOCAL_OS_MODE ? '演示角色 · 本地查证入口' : npc.role || '村民',
          avatar: npc.avatar_emoji || '👤',
          color: npc.color || 'from-slate-500 to-slate-600',
          greeting: LOCAL_OS_MODE ? '这是原 OS 的演示角色入口，不代表真实村民、传承身份或个人经历。当前从同一工作室知识库检索并摘录，没有生成式模型；你可以问“徽州三雕包括什么？”。' : npc.greeting || `你好，我是${npc.name}。`,
        }
      }
      return npcDataCache
    }
  } catch (err) {
    console.error('Failed to load NPC data:', err)
  }
  
  return DEFAULT_NPC_DATA
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  // Assistant 消息的额外字段
  policyMode?: PolicyMode
  citations?: CitationItem[]
  traceId?: string
  followupQuestions?: string[]
  isError?: boolean
  hasFeedback?: boolean  // 是否已提交纠错
  retrievalMode?: 'extractive'
  evidenceStatus?: 'answered' | 'insufficient_evidence'
}

// ============================================================
// MessageBubble 组件
// ============================================================

interface MessageBubbleProps {
  message: Message
  onFeedback?: (traceId: string, content: string) => void
  onFollowup?: (question: string) => void
}

function MessageBubble({ message, onFeedback, onFollowup }: MessageBubbleProps) {
  const [showCitations, setShowCitations] = useState(false)
  const [showTrace, setShowTrace] = useState(false)
  
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md px-4 py-2.5 bg-primary-500 text-white">
          <p className="text-sm leading-relaxed whitespace-pre-wrap">
            {message.content}
          </p>
        </div>
      </div>
    )
  }
  
  // Assistant 消息
  const hasCitations = message.citations && message.citations.length > 0
  const hasTrace = !!message.traceId
  
  return (
    <div className="flex justify-start">
      <div className={`max-w-[85%] rounded-2xl rounded-bl-md px-4 py-2.5 shadow-sm ${
        message.isError 
          ? 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800' 
          : 'bg-white dark:bg-slate-800'
      }`}>
        {/* 回答文本 */}
        <p className={`text-sm leading-relaxed whitespace-pre-wrap ${
          message.isError 
            ? 'text-red-600 dark:text-red-400' 
            : 'text-slate-900 dark:text-white'
        }`}>
          {message.content}
        </p>
        
        {/* Policy Mode 标签 */}
        {message.policyMode && (
          <div className="mt-2 flex items-center gap-2">
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getPolicyModeColor(message.policyMode)}`}>
              {message.retrievalMode === 'extractive' ? (message.evidenceStatus === 'answered' ? '本地证据摘录 · 有引用' : '本地查证 · 证据不足') : getPolicyModeLabel(message.policyMode)}
            </span>
          </div>
        )}
        
        {/* 折叠区域 */}
        {(hasCitations || hasTrace) && (
          <div className="mt-3 pt-2 border-t border-slate-100 dark:border-slate-700 space-y-2">
            {/* 引用折叠 */}
            {hasCitations && (
              <div>
                <button
                  onClick={() => setShowCitations(!showCitations)}
                  className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                >
                  <BookOpen className="w-3.5 h-3.5" />
                  <span>引用 ({message.citations!.length})</span>
                  {showCitations ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
                
                {showCitations && (
                  <div className="mt-2 space-y-1.5">
                    {message.citations!.map((citation, idx) => (
                      <div 
                        key={citation.evidence_id || idx}
                        className="text-xs bg-slate-50 dark:bg-slate-700/50 rounded px-2 py-1.5"
                      >
                        <div className="font-medium text-slate-700 dark:text-slate-300">
                          {citation.title || `证据 ${idx + 1}`}
                        </div>
                        {citation.source_ref && (
                          <div className="text-slate-500 dark:text-slate-400 mt-0.5">
                            来源: {citation.source_ref}
                          </div>
                        )}
                        {citation.excerpt && (
                          <div className="text-slate-600 dark:text-slate-400 mt-1 line-clamp-2">
                            {citation.excerpt}
                          </div>
                        )}
                        {citation.knowledge_version !== undefined && <div className="mt-1 text-slate-500">知识 v{citation.knowledge_version} · {citation.review_status === 'source_checked' ? '已核对出处' : citation.review_status === 'approved' ? '已审阅' : citation.review_status}</div>}
                        {citation.locator && <div className="mt-1 text-slate-500">定位：{citation.locator}</div>}
                        {citation.region_scope && <div className="mt-1 text-slate-500">范围：{citation.region_scope}</div>}
                        {citation.url && /^https?:\/\//i.test(citation.url) && <a href={citation.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-primary-600 underline">打开原始来源 ↗</a>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            
            {/* Trace 折叠 */}
            {hasTrace && (
              <div>
                <button
                  onClick={() => setShowTrace(!showTrace)}
                  className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                >
                  <Hash className="w-3.5 h-3.5" />
                  <span>{message.retrievalMode === 'extractive' ? '查证记录' : 'Trace'}</span>
                  {showTrace ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
                
                {showTrace && (
                  <div className="mt-1 text-xs text-slate-400 font-mono bg-slate-50 dark:bg-slate-700/50 rounded px-2 py-1">
                    {message.traceId}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        
        {/* 后续问题建议 - 点击即发送 */}
        {message.followupQuestions && message.followupQuestions.length > 0 && (
          <div className="mt-3 pt-2 border-t border-slate-100 dark:border-slate-700">
            <div className="text-xs text-slate-500 mb-1.5">你可能还想问：</div>
            <div className="flex flex-wrap gap-1.5">
              {message.followupQuestions.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => onFollowup?.(q)}
                  className="text-xs bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 px-2 py-1 rounded-full hover:bg-primary-100 dark:hover:bg-primary-900/30 hover:text-primary-600 dark:hover:text-primary-400 transition-colors active:scale-95"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        
        {/* 纠错按钮 - 仅对有 traceId 且非错误的消息显示 */}
        {message.traceId && !message.isError && (
          <div className="mt-3 pt-2 border-t border-slate-100 dark:border-slate-700">
            {message.hasFeedback ? (
              <div className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                <Flag className="w-3.5 h-3.5" />
                <span>已纠错</span>
              </div>
            ) : (
              <button
                onClick={() => onFeedback?.(message.traceId!, message.content)}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-amber-500 dark:hover:text-amber-400 transition-colors"
              >
                <Flag className="w-3.5 h-3.5" />
                <span>纠错 / 不准确</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================================
// 主页面组件
// ============================================================

export default function NPCChatPage() {
  const params = useParams()
  const router = useRouter()
  const npcId = params.npc_id as string
  
  // NPC 数据状态
  const [npc, setNpc] = useState<{ name: string; title: string; avatar: string; color: string; greeting: string } | null>(null)
  const [npcLoading, setNpcLoading] = useState(true)
  
  const [sessionId, setSessionId] = useState<string>('')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  // 纠错弹窗状态
  const [feedbackModal, setFeedbackModal] = useState<{
    isOpen: boolean
    traceId: string
    content: string
  }>({ isOpen: false, traceId: '', content: '' })
  
  // 已提交纠错的 trace_id 集合（防重复提交）
  const [submittedFeedbacks, setSubmittedFeedbacks] = useState<Set<string>>(new Set())
  
  // 加载 NPC 数据
  useEffect(() => {
    async function loadNPC() {
      setNpcLoading(true)
      const npcData = await loadNPCData()
      const currentNpc = npcData[npcId] || DEFAULT_NPC_DATA[npcId]
      setNpc(currentNpc || null)
      
      // 设置初始问候消息
      if (currentNpc) {
        setMessages([{
          id: '1',
          role: 'assistant',
          content: currentNpc.greeting || '你好，有什么可以帮助你的？',
        }])
      }
      setNpcLoading(false)
    }
    
    if (npcId) {
      loadNPC()
    }
  }, [npcId])
  
  // 初始化 session
  useEffect(() => {
    if (npcId) {
      const sid = getOrCreateSessionId(npcId)
      setSessionId(sid)
    }
  }, [npcId])
  
  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])
  
  // 加载中
  if (npcLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100 dark:bg-slate-900">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    )
  }

  if (!npc) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100 dark:bg-slate-900">
        <div className="text-center">
          <p className="text-slate-500 dark:text-slate-400">NPC 不存在</p>
          <button
            onClick={() => router.push('/')}
            className="mt-4 px-4 py-2 bg-primary-500 text-white rounded-lg"
          >
            返回首页
          </button>
        </div>
      </div>
    )
  }
  
  const handleSend = async () => {
    if (!input.trim() || isLoading) return
    
    const query = input.trim()
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: query,
    }
    
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)
    setError(null)
    
    // 调用 AI Orchestrator API
    const result = await npcChat(npcId, query, sessionId)
    
    if (isNPCChatError(result)) {
      // 错误处理
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: result.message,
        isError: true,
      }
      setMessages((prev) => [...prev, errorMessage])
      setError(result.message)
      setInput(query)
    } else {
      // 成功响应
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: result.answer_text,
        policyMode: result.policy_mode,
        citations: result.citations,
        traceId: result.trace_id,
        followupQuestions: result.followup_questions,
        retrievalMode: result.retrieval_mode,
        evidenceStatus: result.evidence_status,
      }
      setMessages((prev) => [...prev, assistantMessage])
    }
    
    setIsLoading(false)
  }
  
  // 打开纠错弹窗
  const handleOpenFeedback = (traceId: string, content: string) => {
    // 检查是否已提交过
    if (submittedFeedbacks.has(traceId)) {
      return
    }
    setFeedbackModal({ isOpen: true, traceId, content })
  }
  
  // 纠错提交成功
  const handleFeedbackSuccess = () => {
    const traceId = feedbackModal.traceId
    // 添加到已提交集合
    setSubmittedFeedbacks((prev) => new Set(prev).add(traceId))
    // 更新消息的 hasFeedback 标记
    setMessages((prev) =>
      prev.map((msg) =>
        msg.traceId === traceId ? { ...msg, hasFeedback: true } : msg
      )
    )
  }
  
  // 点击后续问题即发送
  const handleFollowup = async (question: string) => {
    if (isLoading) return
    
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: question,
    }
    
    setMessages((prev) => [...prev, userMessage])
    setIsLoading(true)
    setError(null)
    
    const result = await npcChat(npcId, question, sessionId)
    
    if (isNPCChatError(result)) {
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: result.message,
        isError: true,
      }
      setMessages((prev) => [...prev, errorMessage])
      setError(result.message)
    } else {
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: result.answer_text,
        policyMode: result.policy_mode,
        citations: result.citations,
        traceId: result.trace_id,
        followupQuestions: result.followup_questions,
        retrievalMode: result.retrieval_mode,
        evidenceStatus: result.evidence_status,
      }
      setMessages((prev) => [...prev, assistantMessage])
    }
    
    setIsLoading(false)
  }
  
  const handleResetChat = () => {
    // 清除当前 NPC 的 session
    clearSessionId(npcId)
    // 生成新 session
    const newSessionId = getOrCreateSessionId(npcId)
    setSessionId(newSessionId)
    // 重置消息
    setMessages([
      {
        id: '1',
        role: 'assistant',
        content: npc?.greeting || '你好，有什么可以帮助你的？',
      },
    ])
  }
  
  return (
    <div className="h-[100dvh] flex flex-col bg-slate-100 dark:bg-slate-900 overflow-hidden">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-white/80 dark:bg-slate-800/80 backdrop-blur-lg border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-3 px-4 py-3">
          <button
            onClick={() => router.push('/')}
            className="p-2 -ml-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-slate-600 dark:text-slate-300" />
          </button>
          
          <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${npc.color} flex items-center justify-center text-xl`}>
            {npc.avatar}
          </div>
          
          <div className="flex-1 min-w-0">
            <h1 className="font-semibold text-slate-900 dark:text-white truncate">
              {npc.name}
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {npc.title}
            </p>
          </div>
          
          <button
            onClick={handleResetChat}
            className="p-2 rounded-full hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            title="重置对话"
          >
            <RotateCcw className="w-5 h-5 text-slate-600 dark:text-slate-300" />
          </button>
        </div>
      </header>

      {LOCAL_OS_MODE && <div className="border-b border-emerald-200 bg-emerald-50 px-4 py-2 text-xs leading-relaxed text-emerald-800">本地证据检索 · 没有生成式模型或已训练权重。与<a href="/studio/#knowledge" className="underline">文明工作室</a>使用同一知识库；区域资料不能自动证明严田村史。</div>}
      
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map((message) => (
          <MessageBubble 
            key={message.id} 
            message={message} 
            onFeedback={handleOpenFeedback}
            onFollowup={handleFollowup}
          />
        ))}
        
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white dark:bg-slate-800 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          </div>
        )}
        
        {/* 滚动锚点 */}
        <div ref={messagesEndRef} />
      </div>
      
      {/* 纠错弹窗 */}
      <FeedbackModal
        isOpen={feedbackModal.isOpen}
        onClose={() => setFeedbackModal({ isOpen: false, traceId: '', content: '' })}
        traceId={feedbackModal.traceId}
        originalResponse={feedbackModal.content}
        onSuccess={handleFeedbackSuccess}
      />
      
      {/* Input */}
      <div className="flex-shrink-0 bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 px-4 py-3 safe-area-inset-bottom">
        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder="输入消息..."
              rows={1}
              className="w-full px-4 py-2.5 bg-slate-100 dark:bg-slate-700 rounded-2xl text-sm text-slate-900 dark:text-white placeholder-slate-400 resize-none focus:outline-none focus:ring-2 focus:ring-primary-500"
              style={{ maxHeight: '120px' }}
            />
          </div>
          
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-colors ${
              input.trim() && !isLoading
                ? 'bg-primary-500 text-white'
                : 'bg-slate-200 dark:bg-slate-700 text-slate-400'
            }`}
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  )
}
