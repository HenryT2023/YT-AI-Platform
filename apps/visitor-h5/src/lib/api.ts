/**
 * API Client
 * 
 * 封装 ai-orchestrator 和 core-backend 的 API 调用
 */

import { AI_ORCH_BASE, CORE_BASE, TENANT_ID, SITE_ID } from './config'

// ============================================================
// Types
// ============================================================

export interface CitationItem {
  evidence_id: string
  title?: string
  source_ref?: string
  excerpt?: string
  confidence: number
}

export type PolicyMode = 'normal' | 'conservative' | 'refuse'

export interface NPCChatResponse {
  trace_id: string
  session_id: string
  policy_mode: PolicyMode
  answer_text: string
  citations: CitationItem[]
  followup_questions: string[]
  npc_name?: string
  latency_ms?: number
  timestamp: string
}

export interface NPCChatError {
  error: true
  message: string
  status?: number
  trace_id?: string
}

export type NPCChatResult = NPCChatResponse | NPCChatError

// ============================================================
// API Functions
// ============================================================

/**
 * NPC 对话
 * 
 * @param npcId NPC ID
 * @param query 用户问题
 * @param sessionId 会话 ID
 * @returns 对话响应或错误
 */
export async function npcChat(
  npcId: string,
  query: string,
  sessionId: string,
): Promise<NPCChatResult> {
  const url = `${AI_ORCH_BASE}/api/v1/npc/chat`
  
  const body = {
    tenant_id: TENANT_ID,
    site_id: SITE_ID,
    npc_id: npcId,
    query,
    session_id: sessionId,
  }
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      return {
        error: true,
        message: errorData.detail || `请求失败: ${response.status}`,
        status: response.status,
      }
    }
    
    const data: NPCChatResponse = await response.json()
    return data
    
  } catch (err) {
    // 网络错误或超时
    const message = err instanceof Error ? err.message : '网络请求失败'
    return {
      error: true,
      message: message.includes('fetch') ? '无法连接到服务器' : message,
    }
  }
}

/**
 * 判断响应是否为错误
 */
export function isNPCChatError(result: NPCChatResult): result is NPCChatError {
  return 'error' in result && result.error === true
}

/**
 * 获取 policy_mode 的中文标签
 */
export function getPolicyModeLabel(mode: PolicyMode): string {
  switch (mode) {
    case 'normal':
      return '正常'
    case 'conservative':
      return '保守'
    case 'refuse':
      return '拒绝'
    default:
      return mode
  }
}

/**
 * 获取 policy_mode 的颜色类名
 */
export function getPolicyModeColor(mode: PolicyMode): string {
  switch (mode) {
    case 'normal':
      return 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
    case 'conservative':
      return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300'
    case 'refuse':
      return 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300'
    default:
      return 'bg-gray-100 text-gray-700'
  }
}

// ============================================================
// Feedback API
// ============================================================

export type FeedbackType = 'fact_error' | 'unsafe' | 'other'
export type FeedbackSeverity = 'low' | 'medium' | 'high'

export interface FeedbackRequest {
  tenant_id: string
  site_id: string
  trace_id: string
  feedback_type: FeedbackType
  severity: FeedbackSeverity
  content: string
  suggested_fix?: string
}

export interface FeedbackResponse {
  id: string
  trace_id: string
  feedback_type: string
  severity: string
  status: string
  created_at: string
}

export interface FeedbackError {
  error: true
  message: string
  status?: number
}

export type FeedbackResult = FeedbackResponse | FeedbackError

/**
 * 提交纠错反馈
 */
export async function submitFeedback(
  request: FeedbackRequest,
): Promise<FeedbackResult> {
  const url = `${CORE_BASE}/api/v1/feedback`
  
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      return {
        error: true,
        message: errorData.detail || `提交失败: ${response.status}`,
        status: response.status,
      }
    }
    
    const data: FeedbackResponse = await response.json()
    return data
    
  } catch (err) {
    const message = err instanceof Error ? err.message : '网络请求失败'
    return {
      error: true,
      message: message.includes('fetch') ? '无法连接到服务器' : message,
    }
  }
}

/**
 * 判断响应是否为错误
 */
export function isFeedbackError(result: FeedbackResult): result is FeedbackError {
  return 'error' in result && result.error === true
}
