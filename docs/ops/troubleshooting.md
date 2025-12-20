# 故障处理手册

## 1. 快速诊断

### 1.1 服务状态检查

```bash
# 检查所有服务状态
docker-compose ps

# 检查服务健康
curl -s http://localhost:8000/api/health | jq
curl -s http://localhost:8001/health | jq
```

### 1.2 日志查看

```bash
# 实时日志
docker-compose logs -f --tail=100 core-backend

# 错误日志
docker-compose logs core-backend 2>&1 | grep -i error

# 特定时间段日志
docker-compose logs --since="2024-01-01T00:00:00" core-backend
```

### 1.3 资源监控

```bash
# 容器资源使用
docker stats

# 磁盘使用
df -h

# 内存使用
free -h
```

## 2. 常见故障

### 2.1 服务无法启动

**症状**：`docker-compose up` 后服务退出

**排查步骤**：

1. 查看退出日志
```bash
docker-compose logs core-backend | tail -50
```

2. 检查环境变量
```bash
docker-compose config
```

3. 检查端口占用
```bash
lsof -i :8000
```

**解决方案**：

- 端口被占用：修改 `.env` 中的端口配置
- 依赖服务未就绪：检查 postgres/redis 是否正常
- 配置错误：检查环境变量是否正确

### 2.2 数据库连接失败

**症状**：`Connection refused` 或 `timeout`

**排查步骤**：

```bash
# 检查 PostgreSQL 状态
docker-compose exec postgres pg_isready -U yantian

# 测试连接
docker-compose exec core-backend python -c "
from app.database.engine import engine
import asyncio
asyncio.run(engine.connect())
print('OK')
"
```

**解决方案**：

- 检查 `DATABASE_URL` 配置
- 确认 PostgreSQL 容器正常运行
- 检查网络连接

### 2.3 Redis 连接失败

**症状**：缓存不生效或会话丢失

**排查步骤**：

```bash
# 检查 Redis 状态
docker-compose exec redis redis-cli ping

# 检查内存使用
docker-compose exec redis redis-cli info memory
```

**解决方案**：

- 检查 `REDIS_URL` 配置
- 清理 Redis 内存：`redis-cli FLUSHALL`
- 重启 Redis 服务

### 2.4 LLM 调用失败

**症状**：对话无响应或返回错误

**排查步骤**：

```bash
# 检查 API Key
echo $OPENAI_API_KEY

# 测试 API 连通性
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

**解决方案**：

- 检查 `OPENAI_API_KEY` 是否正确
- 检查网络是否能访问 OpenAI API
- 检查 API 配额是否用尽

### 2.5 向量检索失败

**症状**：语义搜索无结果

**排查步骤**：

```bash
# 检查 Qdrant 状态
curl http://localhost:6333/collections

# 检查 Collection 数据
curl http://localhost:6333/collections/knowledge
```

**解决方案**：

- 确认 Qdrant 服务正常
- 重新运行向量化脚本
- 检查 Embedding API 是否正常

### 2.6 API 响应慢

**症状**：接口响应时间 > 1s

**排查步骤**：

```bash
# 检查慢查询
docker-compose exec postgres psql -U yantian -c "
SELECT query, calls, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
"

# 检查缓存命中率
curl http://localhost:8000/metrics | grep cache
```

**解决方案**：

- 添加数据库索引
- 启用缓存
- 优化慢查询

## 3. 恢复操作

### 3.1 服务重启

```bash
# 重启单个服务
docker-compose restart core-backend

# 重启所有服务
docker-compose restart

# 完全重建
docker-compose down && docker-compose up -d
```

### 3.2 数据库恢复

```bash
# 从备份恢复
docker-compose exec -T postgres psql -U yantian < backup.sql

# 回滚迁移
docker-compose exec core-backend alembic downgrade -1
```

### 3.3 清理缓存

```bash
# 清理 Redis 缓存
docker-compose exec redis redis-cli FLUSHDB

# 清理本地缓存（重启服务）
docker-compose restart core-backend
```

## 4. 监控告警

### 4.1 关键指标

| 指标 | 阈值 | 告警级别 |
|------|------|----------|
| API P99 延迟 | > 500ms | Warning |
| API 错误率 | > 1% | Critical |
| CPU 使用率 | > 80% | Warning |
| 内存使用率 | > 85% | Warning |
| 磁盘使用率 | > 90% | Critical |

### 4.2 Prometheus 查询

```promql
# API 错误率
sum(rate(http_requests_total{status_code=~"5.."}[5m]))
/ sum(rate(http_requests_total[5m]))

# P99 延迟
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# LLM 调用失败率
sum(rate(llm_requests_total{status="error"}[5m]))
/ sum(rate(llm_requests_total[5m]))
```

## 5. 联系方式

- **技术负责人**：xxx@example.com
- **运维值班**：xxx@example.com
- **紧急电话**：138-xxxx-xxxx
