# Visitor H5

严田 AI 文明引擎 - 游客 H5 端

## 功能

- 移动端优先的响应式设计
- NPC 选择与对话界面
- 支持深色/浅色模式

## 本地开发

```bash
# 安装依赖
cd apps/visitor-h5
npm install

# 启动开发服务器
npm run dev
```

访问 http://localhost:3001

## 环境变量

复制 `.env.example` 到 `.env.local` 并配置：

```env
NEXT_PUBLIC_AI_ORCH_URL=http://localhost:8001
NEXT_PUBLIC_CORE_BACKEND_URL=http://localhost:8000
NEXT_PUBLIC_TENANT_ID=yantian
NEXT_PUBLIC_SITE_ID=yantian-main
```

## 页面结构

- `/` - 入口页，展示 NPC 列表
- `/npc/[npc_id]` - NPC 对话页

## 技术栈

- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Lucide Icons
