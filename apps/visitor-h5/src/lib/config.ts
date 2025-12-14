/**
 * 应用配置
 * 统一管理环境变量和 API 路径常量
 */

// API 基础路径
export const AI_ORCH_BASE = process.env.NEXT_PUBLIC_AI_ORCH_URL || 'http://localhost:8001'
export const CORE_BASE = process.env.NEXT_PUBLIC_CORE_BACKEND_URL || 'http://localhost:8000'

// 租户和站点
export const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID || 'yantian'
export const SITE_ID = process.env.NEXT_PUBLIC_SITE_ID || 'yantian-main'

// API 端点
export const API = {
  // AI Orchestrator
  chat: `${AI_ORCH_BASE}/api/v1/chat`,
  stream: `${AI_ORCH_BASE}/api/v1/chat/stream`,
  
  // Core Backend
  npcs: `${CORE_BASE}/api/v1/npcs`,
  sessions: `${CORE_BASE}/api/v1/sessions`,
} as const
