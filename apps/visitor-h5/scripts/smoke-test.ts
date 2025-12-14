/**
 * visitor-h5 灰度验收测试脚本
 * 
 * 使用方法:
 * 1. npx playwright install chromium
 * 2. npx ts-node scripts/smoke-test.ts
 * 
 * 或者直接运行:
 * npx playwright test scripts/smoke-test.ts
 */

import { chromium, devices } from 'playwright'

const BASE_URL = process.env.TEST_URL || 'http://localhost:3001'
const QUESTIONS = [
  '严田村的历史有多久？',
  '村里有什么传统习俗？',
  '严氏家训有哪些？',
  '村里有什么特色美食？',
  '非遗手艺有哪些？',
  '年轻人回乡创业做什么？',
  '村里的老建筑有哪些？',
  '严田村的地理位置在哪？',
  '村里有多少户人家？',
  '最近有什么活动？',
]

interface TestResult {
  name: string
  passed: boolean
  duration: number
  error?: string
}

const results: TestResult[] = []

async function runTest(name: string, fn: () => Promise<void>): Promise<void> {
  const start = Date.now()
  try {
    await fn()
    results.push({ name, passed: true, duration: Date.now() - start })
    console.log(`✅ ${name} (${Date.now() - start}ms)`)
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err)
    results.push({ name, passed: false, duration: Date.now() - start, error })
    console.log(`❌ ${name}: ${error}`)
  }
}

async function main() {
  console.log('\n🧪 visitor-h5 灰度验收测试')
  console.log(`📍 目标: ${BASE_URL}`)
  console.log('=' .repeat(50))

  const browser = await chromium.launch({ headless: false })
  const context = await browser.newContext({
    ...devices['iPhone 13'],
  })
  const page = await context.newPage()

  // Test 1: 首页加载
  await runTest('首页加载', async () => {
    await page.goto(BASE_URL)
    await page.waitForSelector('text=严田 AI', { timeout: 10000 })
  })

  // Test 2: 健康检查页面
  await runTest('健康检查页面', async () => {
    await page.goto(`${BASE_URL}/health`)
    await page.waitForSelector('text=系统状态', { timeout: 10000 })
    // 等待检测完成（客户端渲染需要时间）
    await page.waitForTimeout(5000)
    // 检查是否显示服务状态文字
    const okCount = await page.locator('text=所有服务正常').count()
    const failCount = await page.locator('text=部分服务异常').count()
    if (okCount === 0 && failCount === 0) {
      throw new Error('未显示服务状态')
    }
  })

  // Test 3: 进入 NPC 对话
  await runTest('进入 NPC 对话', async () => {
    await page.goto(BASE_URL)
    await page.waitForSelector('text=陈老伯', { timeout: 5000 })
    await page.click('text=陈老伯')
    await page.waitForSelector('text=村中长者', { timeout: 5000 })
  })

  // Test 4-13: 连续发送 10 个问题
  let messageCount = 1 // 初始有欢迎语
  for (let i = 0; i < QUESTIONS.length; i++) {
    const question = QUESTIONS[i]
    await runTest(`问题 ${i + 1}: ${question.slice(0, 15)}...`, async () => {
      // 等待输入框可用
      await page.waitForSelector('textarea', { timeout: 5000 })
      // 输入问题
      await page.fill('textarea', question)
      // 点击发送按钮
      await page.locator('button').filter({ has: page.locator('svg.lucide-send') }).click()
      // 等待加载指示器消失（表示回复完成）
      await page.waitForSelector('.animate-spin', { state: 'visible', timeout: 5000 }).catch(() => {})
      await page.waitForSelector('.animate-spin', { state: 'hidden', timeout: 60000 })
      messageCount++
      // 等待一下确保 UI 更新
      await page.waitForTimeout(500)
    })
  }

  // Test 14: 纠错功能（需要真实 AI 服务返回 trace_id）
  await runTest('纠错功能', async () => {
    // 滚动页面查找纠错按钮
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    await page.waitForTimeout(1000)
    
    // 检查是否有纠错按钮（只有真实 AI 响应才有 trace_id）
    const feedbackBtnCount = await page.getByText('纠错 / 不准确').count()
    if (feedbackBtnCount === 0) {
      console.log('  ⚠️ 未找到纠错按钮（可能是 mock 模式，无 trace_id）')
      return // 跳过此测试
    }
    
    const feedbackBtn = page.getByText('纠错 / 不准确').first()
    await feedbackBtn.click()
    
    // 等待弹窗出现
    await page.waitForSelector('text=提交纠错反馈', { timeout: 5000 })
    
    // 选择错误类型
    await page.getByText('事实不准确').click()
    
    // 填写问题描述
    const textarea = page.locator('textarea').first()
    await textarea.fill('自动化测试 - 测试纠错功能')
    
    // 点击提交按钮
    await page.getByRole('button', { name: '提交' }).click()
    
    // 等待成功提示
    await page.waitForTimeout(3000)
  })

  // Test 15: 重置对话
  await runTest('重置对话', async () => {
    await page.click('[title="重置对话"]')
    await page.waitForTimeout(1000)
    // 验证消息被清空
    const messages = await page.locator('.flex.justify-end').count()
    if (messages > 0) {
      throw new Error('消息未清空')
    }
  })

  await browser.close()

  // 输出结果汇总
  console.log('\n' + '='.repeat(50))
  console.log('📊 测试结果汇总')
  console.log('='.repeat(50))
  
  const passed = results.filter(r => r.passed).length
  const failed = results.filter(r => !r.passed).length
  const totalTime = results.reduce((sum, r) => sum + r.duration, 0)
  
  console.log(`✅ 通过: ${passed}`)
  console.log(`❌ 失败: ${failed}`)
  console.log(`⏱️  总耗时: ${(totalTime / 1000).toFixed(1)}s`)
  
  if (failed > 0) {
    console.log('\n❌ 失败的测试:')
    results.filter(r => !r.passed).forEach(r => {
      console.log(`  - ${r.name}: ${r.error}`)
    })
  }
  
  console.log('\n' + (failed === 0 ? '🎉 全部通过！' : '⚠️ 存在失败项，请检查'))
  
  process.exit(failed > 0 ? 1 : 0)
}

main().catch(console.error)
