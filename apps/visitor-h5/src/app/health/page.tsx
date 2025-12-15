'use client'

import { useState, useEffect } from 'react'
import { RefreshCw, CheckCircle, XCircle, Clock, Server } from 'lucide-react'
import Link from 'next/link'
import { AI_ORCH_BASE, CORE_BASE, TENANT_ID, SITE_ID } from '@/lib/config'

interface ServiceStatus {
  name: string
  url: string
  status: 'checking' | 'ok' | 'fail'
  latency?: number
  error?: string
  details?: Record<string, unknown>
}

async function checkService(name: string, url: string): Promise<ServiceStatus> {
  const startTime = performance.now()
  
  try {
    const response = await fetch(url, {
      method: 'GET',
      cache: 'no-store',
    })
    
    const latency = Math.round(performance.now() - startTime)
    
    if (!response.ok) {
      return {
        name,
        url,
        status: 'fail',
        latency,
        error: `HTTP ${response.status}`,
      }
    }
    
    const data = await response.json().catch(() => ({}))
    
    return {
      name,
      url,
      status: 'ok',
      latency,
      details: data,
    }
  } catch (err) {
    const latency = Math.round(performance.now() - startTime)
    return {
      name,
      url,
      status: 'fail',
      latency,
      error: err instanceof Error ? err.message : '连接失败',
    }
  }
}

export default function HealthPage() {
  const [services, setServices] = useState<ServiceStatus[]>([
    { name: 'AI Orchestrator', url: `${AI_ORCH_BASE}/health`, status: 'checking' },
    { name: 'Core Backend', url: `${CORE_BASE}/health`, status: 'checking' },
  ])
  const [lastCheck, setLastCheck] = useState<Date | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const checkAllServices = async () => {
    setIsRefreshing(true)
    
    // 并行检测所有服务
    const results = await Promise.all(
      services.map((s) => checkService(s.name, s.url))
    )
    
    setServices(results)
    setLastCheck(new Date())
    setIsRefreshing(false)
  }

  useEffect(() => {
    checkAllServices()
  }, [])

  const allOk = services.every((s) => s.status === 'ok')
  const anyFail = services.some((s) => s.status === 'fail')

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-900 px-4 py-6 safe-area-inset-top safe-area-inset-bottom">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-white">系统状态</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">服务健康检查</p>
        </div>
        <button
          onClick={checkAllServices}
          disabled={isRefreshing}
          className="p-2 rounded-full bg-white dark:bg-slate-800 shadow-sm hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-5 h-5 text-slate-600 dark:text-slate-300 ${isRefreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Overall Status */}
      <div className={`rounded-xl p-4 mb-6 ${
        allOk 
          ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
          : anyFail
            ? 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
            : 'bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700'
      }`}>
        <div className="flex items-center gap-3">
          {allOk ? (
            <CheckCircle className="w-8 h-8 text-green-500" />
          ) : anyFail ? (
            <XCircle className="w-8 h-8 text-red-500" />
          ) : (
            <Clock className="w-8 h-8 text-slate-400 animate-pulse" />
          )}
          <div>
            <div className={`font-semibold ${
              allOk ? 'text-green-700 dark:text-green-300' : anyFail ? 'text-red-700 dark:text-red-300' : 'text-slate-700 dark:text-slate-300'
            }`}>
              {allOk ? '所有服务正常' : anyFail ? '部分服务异常' : '检测中...'}
            </div>
            {lastCheck && (
              <div className="text-xs text-slate-500 dark:text-slate-400">
                上次检测: {lastCheck.toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Service List */}
      <div className="space-y-3 mb-6">
        {services.map((service) => (
          <div
            key={service.name}
            className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Server className="w-5 h-5 text-slate-400" />
                <div>
                  <div className="font-medium text-slate-900 dark:text-white">
                    {service.name}
                  </div>
                  <div className="text-xs text-slate-400 font-mono truncate max-w-[200px]">
                    {service.url}
                  </div>
                </div>
              </div>
              
              <div className="flex items-center gap-2">
                {service.latency !== undefined && (
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    {service.latency}ms
                  </span>
                )}
                {service.status === 'checking' ? (
                  <div className="w-6 h-6 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center">
                    <Clock className="w-4 h-4 text-slate-400 animate-pulse" />
                  </div>
                ) : service.status === 'ok' ? (
                  <div className="w-6 h-6 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                    <CheckCircle className="w-4 h-4 text-green-500" />
                  </div>
                ) : (
                  <div className="w-6 h-6 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                    <XCircle className="w-4 h-4 text-red-500" />
                  </div>
                )}
              </div>
            </div>
            
            {service.error && (
              <div className="mt-2 text-xs text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded px-2 py-1">
                {service.error}
              </div>
            )}
            
            {service.details && Object.keys(service.details).length > 0 && (
              <div className="mt-2 text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-700/50 rounded px-2 py-1 font-mono">
                {JSON.stringify(service.details, null, 0).slice(0, 100)}
                {JSON.stringify(service.details).length > 100 && '...'}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Environment Info */}
      <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
        <h2 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">环境信息</h2>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-slate-500 dark:text-slate-400">Tenant ID</span>
            <span className="font-mono text-slate-900 dark:text-white">{TENANT_ID}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500 dark:text-slate-400">Site ID</span>
            <span className="font-mono text-slate-900 dark:text-white">{SITE_ID}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500 dark:text-slate-400">当前时间</span>
            <span className="text-slate-900 dark:text-white">
              {new Date().toLocaleString('zh-CN')}
            </span>
          </div>
        </div>
      </div>

      {/* Back Link */}
      <div className="mt-6 text-center">
        <Link
          href="/"
          className="text-sm text-primary-500 hover:text-primary-600 dark:hover:text-primary-400"
        >
          ← 返回首页
        </Link>
      </div>
    </div>
  )
}
