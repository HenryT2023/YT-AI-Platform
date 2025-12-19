/**
 * Session 管理
 * 
 * Session ID 格式: session:${tenant}:${site}:${npc_id}
 * 确保不同 NPC 的对话上下文隔离
 */

import { TENANT_ID, SITE_ID } from './config'

const SESSION_STORAGE_PREFIX = 'yt_session'

/**
 * 生成 session storage key
 * 格式: yt_session:${tenant}:${site}:${npc_id}
 */
export function getSessionKey(npcId: string): string {
  return `${SESSION_STORAGE_PREFIX}:${TENANT_ID}:${SITE_ID}:${npcId}`
}

/**
 * 获取指定 NPC 的 session_id
 * 如果不存在则返回 null
 */
export function getSessionId(npcId: string): string | null {
  if (typeof window === 'undefined') return null
  
  const key = getSessionKey(npcId)
  return localStorage.getItem(key)
}

/**
 * 保存 session_id
 */
export function setSessionId(npcId: string, sessionId: string): void {
  if (typeof window === 'undefined') return
  
  const key = getSessionKey(npcId)
  localStorage.setItem(key, sessionId)
}

/**
 * 清除指定 NPC 的 session_id
 */
export function clearSessionId(npcId: string): void {
  if (typeof window === 'undefined') return
  
  const key = getSessionKey(npcId)
  localStorage.removeItem(key)
}

/**
 * 清除所有 session
 */
export function clearAllSessions(): void {
  if (typeof window === 'undefined') return
  
  const keysToRemove: string[] = []
  
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (key?.startsWith(SESSION_STORAGE_PREFIX)) {
      keysToRemove.push(key)
    }
  }
  
  keysToRemove.forEach((key) => localStorage.removeItem(key))
}

/**
 * 生成新的 session_id
 * 格式: sess_${timestamp}_${random}
 */
export function generateSessionId(): string {
  const timestamp = Date.now().toString(36)
  const random = Math.random().toString(36).substring(2, 10)
  return `sess_${timestamp}_${random}`
}

/**
 * 获取或创建 session_id
 * 如果不存在则自动创建并保存
 */
export function getOrCreateSessionId(npcId: string): string {
  let sessionId = getSessionId(npcId)
  
  if (!sessionId) {
    sessionId = generateSessionId()
    setSessionId(npcId, sessionId)
  }
  
  return sessionId
}

// ============================================================
// 全局 Session（用于任务进度等跨 NPC 场景）
// ============================================================

const GLOBAL_SESSION_KEY = `${SESSION_STORAGE_PREFIX}:${TENANT_ID}:${SITE_ID}:_global`

/**
 * 获取全局 session_id
 */
export function getGlobalSessionId(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(GLOBAL_SESSION_KEY)
}

/**
 * 保存全局 session_id
 */
export function setGlobalSessionId(sessionId: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(GLOBAL_SESSION_KEY, sessionId)
}

/**
 * 获取或创建全局 session_id
 * 用于任务进度追踪等跨 NPC 场景
 */
export function getOrCreateGlobalSessionId(): string {
  let sessionId = getGlobalSessionId()
  
  if (!sessionId) {
    sessionId = generateSessionId()
    setGlobalSessionId(sessionId)
  }
  
  return sessionId
}
