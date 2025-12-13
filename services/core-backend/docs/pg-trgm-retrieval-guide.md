# P15 检索过渡升级：Postgres pg_trgm 指南

## 概述

在引入 Qdrant 向量检索前，通过 Postgres pg_trgm 扩展显著提升 `retrieve_evidence` 召回质量，替换传统 LIKE 搜索。

## 核心改进

```text
LIKE 搜索                          pg_trgm 相似度搜索
─────────────────────────────────  ─────────────────────────────────
WHERE title LIKE '%家训%'          WHERE title % '家训'
                                   ORDER BY similarity(title, '家训') DESC

问题：                              优势：
- 必须完全包含子串                  - 支持模糊匹配（错别字容忍）
- 无相关性排序                      - 返回相似度分数
- 无法处理错别字                    - 可设置阈值过滤
- 性能差（全表扫描）                - GIN 索引加速
```

## 文件树变更清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `alembic/versions/004_add_pg_trgm_indexes.py` | 迁移：启用 pg_trgm 扩展和 GIN 索引 |
| `scripts/compare_retrieval_methods.py` | 对比脚本：LIKE vs TRGM 结果差异 |
| `docs/pg-trgm-retrieval-guide.md` | 本文档 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `app/tools/schemas.py` | 添加 `min_score`、`use_trgm`、`retrieval_score`、`score_distribution` 字段 |
| `app/tools/executor.py` | 重写 `retrieve_evidence` 支持 pg_trgm |

## 迁移步骤

### 1. 运行数据库迁移

```bash
cd services/core-backend
alembic upgrade head
```

迁移内容：

```sql
-- 启用 pg_trgm 扩展
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 为 evidences 表添加 GIN 索引
CREATE INDEX ix_evidences_title_trgm ON evidences USING GIN (title gin_trgm_ops);
CREATE INDEX ix_evidences_excerpt_trgm ON evidences USING GIN (excerpt gin_trgm_ops);

-- 为 contents 表添加 GIN 索引
CREATE INDEX ix_contents_title_trgm ON contents USING GIN (title gin_trgm_ops);
CREATE INDEX ix_contents_body_trgm ON contents USING GIN (body gin_trgm_ops);
```

### 2. 验证扩展安装

```sql
-- 检查扩展是否安装
SELECT * FROM pg_extension WHERE extname = 'pg_trgm';

-- 测试相似度函数
SELECT similarity('严氏家训', '严氏家规');
-- 预期输出: 0.5 左右
```

## API 变更

### retrieve_evidence 输入

```json
{
  "query": "严氏家训",
  "domains": ["家训", "文化"],
  "limit": 5,
  "min_score": 0.3,
  "use_trgm": true
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | 必填 | 搜索关键词 |
| `domains` | string[] | null | 知识领域过滤 |
| `limit` | int | 5 | 返回数量限制 (1-20) |
| `min_score` | float | 0.3 | 最小相似度阈值 (0-1) |
| `use_trgm` | bool | true | 是否使用 pg_trgm |

### retrieve_evidence 输出

```json
{
  "items": [
    {
      "id": "uuid-xxx",
      "source_type": "genealogy",
      "title": "严氏家训十则",
      "excerpt": "孝悌为本，耕读传家...",
      "confidence": 0.95,
      "verified": true,
      "tags": ["家训", "文化"],
      "retrieval_score": 0.72
    }
  ],
  "total": 3,
  "query": "严氏家训",
  "search_method": "trgm",
  "score_distribution": {
    "min": 0.45,
    "max": 0.72,
    "avg": 0.58,
    "count": 3
  }
}
```

| 字段 | 说明 |
|------|------|
| `retrieval_score` | 每条结果的相似度分数 |
| `search_method` | 搜索方法：`trgm` 或 `like` |
| `score_distribution` | 分数分布统计 |

## 对比脚本使用

```bash
# 基本用法
python scripts/compare_retrieval_methods.py --query "严氏家训"

# 指定租户和站点
python scripts/compare_retrieval_methods.py \
  --query "祠堂建筑" \
  --tenant yantian \
  --site yantian-main \
  --limit 10

# 调整相似度阈值
python scripts/compare_retrieval_methods.py \
  --query "家训" \
  --min-score 0.2

# JSON 输出
python scripts/compare_retrieval_methods.py \
  --query "严氏家训" \
  --json
```

### 输出示例

```text
================================================================================
查询: 严氏家训
================================================================================

## LIKE 结果
----------------------------------------
1. [abc12345] 严氏家训十则
   confidence: 0.95
   excerpt: 孝悌为本，耕读传家，勤俭持家...

## TRGM 结果
----------------------------------------
1. [abc12345] 严氏家训十则
   retrieval_score: 0.720, confidence: 0.95
   excerpt: 孝悌为本，耕读传家，勤俭持家...
2. [def67890] 严氏家规
   retrieval_score: 0.450, confidence: 0.85
   excerpt: 家规者，治家之法也...

## 差异分析
----------------------------------------
LIKE 命中数: 1
TRGM 命中数: 2
仅 LIKE 命中: 0
仅 TRGM 命中: 1
两者都命中: 1

召回率变化: +100.0%
================================================================================
```

## 相似度阈值调优

| 阈值 | 效果 | 适用场景 |
|------|------|----------|
| 0.1 | 非常宽松，召回率高但精度低 | 探索性搜索 |
| 0.3 | 默认值，平衡召回和精度 | 一般场景 |
| 0.5 | 较严格，精度高但可能漏召 | 精确匹配 |
| 0.7 | 非常严格，几乎完全匹配 | 去重检测 |

## 性能对比

| 指标 | LIKE | pg_trgm |
|------|------|---------|
| 索引类型 | 无（全表扫描） | GIN 索引 |
| 10万条数据查询 | ~500ms | ~50ms |
| 错别字容忍 | ❌ | ✅ |
| 相关性排序 | ❌ | ✅ |
| 分数输出 | ❌ | ✅ |

## 审计日志

每次检索会记录：

```json
{
  "event": "retrieve_evidence_trgm",
  "query": "严氏家训",
  "hit_count": 3,
  "score_distribution": {
    "min": 0.45,
    "max": 0.72,
    "avg": 0.58,
    "count": 3
  }
}
```

## 风险点与缓解

| 风险点 | 说明 | 缓解措施 |
|--------|------|----------|
| **扩展依赖** | 需要 pg_trgm 扩展 | 迁移脚本自动安装 |
| **阈值过高** | 可能漏召重要结果 | 默认 0.3，可调整 |
| **阈值过低** | 返回不相关结果 | 结合 confidence 排序 |
| **中文分词** | pg_trgm 按字符切分 | 后续可接入分词器 |
| **回退兼容** | 旧代码可能依赖 LIKE | 保留 use_trgm=false 选项 |

## 下一步

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1 | **Qdrant 向量检索** | 语义级别相似度 |
| P2 | **中文分词** | jieba + pg_trgm 结合 |
| P3 | **混合检索** | 关键词 + 向量融合 |
| P4 | **检索缓存** | Redis 缓存热门查询 |
| P5 | **A/B 测试** | 对比不同阈值效果 |

## 配置说明

```python
# app/tools/schemas.py

class RetrieveEvidenceInput(BaseModel):
    query: str
    domains: Optional[List[str]] = None
    limit: int = Field(5, ge=1, le=20)
    min_score: float = Field(0.3, ge=0.0, le=1.0)  # pg_trgm 阈值
    use_trgm: bool = Field(True)  # 是否使用 pg_trgm
```

## SQL 参考

### 相似度查询

```sql
-- 基本相似度查询
SELECT
    id,
    title,
    similarity(title, '严氏家训') AS score
FROM evidences
WHERE title % '严氏家训'
ORDER BY score DESC
LIMIT 10;

-- 多字段相似度（取最大值）
SELECT
    id,
    title,
    GREATEST(
        COALESCE(similarity(title, '严氏家训'), 0),
        COALESCE(similarity(excerpt, '严氏家训'), 0)
    ) AS score
FROM evidences
WHERE title % '严氏家训' OR excerpt % '严氏家训'
ORDER BY score DESC
LIMIT 10;
```

### 设置全局阈值

```sql
-- 查看当前阈值
SELECT show_limit();

-- 设置阈值（会话级别）
SELECT set_limit(0.3);
```
