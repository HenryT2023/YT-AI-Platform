# ===========================
# visitor-h5 Dockerfile
# 多阶段构建：builder + runner
# ===========================

# -----------------
# Stage 1: Dependencies
# -----------------
FROM node:20-alpine AS deps
WORKDIR /app

# 安装依赖
COPY package.json package-lock.json* ./
RUN npm ci --only=production

# -----------------
# Stage 2: Builder
# -----------------
FROM node:20-alpine AS builder
WORKDIR /app

# 复制依赖
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# 构建参数（用于注入环境变量到构建时）
ARG NEXT_PUBLIC_AI_ORCH_URL=http://localhost:8001
ARG NEXT_PUBLIC_CORE_BACKEND_URL=http://localhost:8000
ARG NEXT_PUBLIC_TENANT_ID=yantian
ARG NEXT_PUBLIC_SITE_ID=yantian-main

ENV NEXT_PUBLIC_AI_ORCH_URL=$NEXT_PUBLIC_AI_ORCH_URL
ENV NEXT_PUBLIC_CORE_BACKEND_URL=$NEXT_PUBLIC_CORE_BACKEND_URL
ENV NEXT_PUBLIC_TENANT_ID=$NEXT_PUBLIC_TENANT_ID
ENV NEXT_PUBLIC_SITE_ID=$NEXT_PUBLIC_SITE_ID

# 禁用 Next.js 遥测
ENV NEXT_TELEMETRY_DISABLED=1

# 构建
RUN npm run build

# -----------------
# Stage 3: Runner
# -----------------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# 创建非 root 用户
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# 复制必要文件
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# 设置权限
USER nextjs

# 暴露端口
EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# 启动
CMD ["node", "server.js"]
