'use client'

import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, Send, Loader2 } from 'lucide-react'
import { useState } from 'react'

const NPC_DATA: Record<string, {
  name: string
  title: string
  avatar: string
  color: string
  greeting: string
}> = {
  npc_elder_chen: {
    name: '陈老伯',
    title: '村中长者',
    avatar: '👴',
    color: 'from-amber-500 to-orange-600',
    greeting: '年轻人，欢迎来到严田村。我在这里生活了七十多年，有什么想知道的尽管问。',
  },
  npc_xiaomei: {
    name: '小美',
    title: '返乡创业青年',
    avatar: '👩',
    color: 'from-pink-500 to-rose-600',
    greeting: '嗨！我是小美，去年从城里回来帮村里搞智慧农业。你对我们的项目感兴趣吗？',
  },
  npc_master_li: {
    name: '李师傅',
    title: '非遗传承人',
    avatar: '👨‍🔧',
    color: 'from-emerald-500 to-teal-600',
    greeting: '欢迎来到我的工坊。这些竹编和木雕都是祖辈传下来的手艺，你想了解哪一样？',
  },
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export default function NPCChatPage() {
  const params = useParams()
  const router = useRouter()
  const npcId = params.npc_id as string
  
  const npc = NPC_DATA[npcId]
  
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: npc?.greeting || '你好，有什么可以帮助你的？',
    },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  
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
    
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    }
    
    setMessages((prev) => [...prev, userMessage])
    setInput('')
    setIsLoading(true)
    
    // TODO: 调用 AI Orchestrator API
    // 目前使用模拟响应
    setTimeout(() => {
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `（${npc.name}正在思考...）这是一个模拟回复。后续会接入 AI Orchestrator 服务。`,
      }
      setMessages((prev) => [...prev, assistantMessage])
      setIsLoading(false)
    }, 1000)
  }
  
  return (
    <div className="min-h-screen flex flex-col bg-slate-100 dark:bg-slate-900">
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
        </div>
      </header>
      
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                message.role === 'user'
                  ? 'bg-primary-500 text-white rounded-br-md'
                  : 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white rounded-bl-md shadow-sm'
              }`}
            >
              <p className="text-sm leading-relaxed whitespace-pre-wrap">
                {message.content}
              </p>
            </div>
          </div>
        ))}
        
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white dark:bg-slate-800 rounded-2xl rounded-bl-md px-4 py-3 shadow-sm">
              <Loader2 className="w-5 h-5 text-slate-400 animate-spin" />
            </div>
          </div>
        )}
      </div>
      
      {/* Input */}
      <div className="sticky bottom-0 bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 px-4 py-3 safe-area-inset-bottom">
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
