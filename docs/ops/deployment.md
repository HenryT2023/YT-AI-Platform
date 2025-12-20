# 部署手册

## 1. 环境要求

### 硬件要求

| 环境 | CPU | 内存 | 磁盘 |
|------|-----|------|------|
| 开发 | 2 核 | 4GB | 20GB |
| 测试 | 4 核 | 8GB | 50GB |
| 生产 | 8 核 | 16GB | 100GB |

### 软件要求

- Docker 24.0+
- Docker Compose 2.20+
- PostgreSQL 15+
- Redis 7+
- Qdrant 1.7+

## 2. 快速部署

### 2.1 克隆代码

```bash
git clone https://github.com/your-org/YT-AI-Platform.git
cd YT-AI-Platform
```

### 2.2 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，配置必要的环境变量
```

**必须配置的变量**：

| 变量 | 说明 | 示例 |
|------|------|------|
| `POSTGRES_PASSWORD` | 数据库密码 | `your-secure-password` |
| `JWT_SECRET_KEY` | JWT 密钥 | `your-jwt-secret-key` |
| `OPENAI_API_KEY` | OpenAI API Key | `sk-xxx` |

### 2.3 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f core-backend
```

### 2.4 初始化数据库

```bash
# 运行数据库迁移
docker-compose exec core-backend alembic upgrade head

# 初始化种子数据
docker-compose exec core-backend python scripts/seed_solar_terms.py
```

### 2.5 验证部署

```bash
# 健康检查
curl http://localhost:8000/api/health

# 预期响应
# {"status": "healthy", "version": "1.0.0"}
```

## 3. 生产部署

### 3.1 使用 Docker Compose

```bash
# 使用生产配置
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 3.2 使用 Kubernetes

```bash
# 应用 Kubernetes 配置
kubectl apply -f k8s/

# 查看 Pod 状态
kubectl get pods -n yantian
```

### 3.3 Nginx 反向代理

```nginx
upstream backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name api.yantian.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.yantian.example.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    location / {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 4. 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| core-backend | 8000 | 核心后端 API |
| ai-orchestrator | 8001 | AI 编排服务 |
| admin-console | 3000 | 管理后台 |
| visitor-h5 | 3001 | 游客端 H5 |
| postgres | 5432 | PostgreSQL |
| redis | 6379 | Redis |
| qdrant | 6333 | Qdrant 向量数据库 |

## 5. 健康检查

### API 健康检查

```bash
# 核心后端
curl http://localhost:8000/api/health

# AI 编排服务
curl http://localhost:8001/health

# 向量服务
curl http://localhost:8000/api/v1/search/health
```

### 数据库连接检查

```bash
docker-compose exec postgres pg_isready -U yantian
```

### Redis 连接检查

```bash
docker-compose exec redis redis-cli ping
```

## 6. 常见问题

### Q: 服务启动失败

检查日志：
```bash
docker-compose logs core-backend
```

常见原因：
- 数据库连接失败：检查 `DATABASE_URL`
- Redis 连接失败：检查 `REDIS_URL`
- 端口被占用：修改 `.env` 中的端口配置

### Q: 数据库迁移失败

```bash
# 查看迁移状态
docker-compose exec core-backend alembic current

# 回滚迁移
docker-compose exec core-backend alembic downgrade -1
```

### Q: 内存不足

调整 Docker 资源限制：
```yaml
# docker-compose.override.yml
services:
  core-backend:
    deploy:
      resources:
        limits:
          memory: 2G
```
