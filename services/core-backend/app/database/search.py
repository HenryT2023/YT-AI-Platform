"""
全文搜索配置

PostgreSQL 全文搜索配置说明：

1. 默认使用 'simple' 配置，适用于基本的中文搜索
2. 对于更好的中文分词效果，建议：
   - 安装 zhparser 扩展：https://github.com/amutu/zhparser
   - 或使用 pg_jieba 扩展：https://github.com/jaiminpan/pg_jieba
3. 生产环境推荐使用 Qdrant 向量检索替代全文搜索

使用示例：
    from app.database.search import search_contents

    results = await search_contents(session, "严氏家训", tenant_id, site_id)
"""

from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Content


async def search_contents(
    session: AsyncSession,
    query: str,
    tenant_id: str,
    site_id: str,
    content_type: Optional[str] = None,
    limit: int = 20,
) -> List[Content]:
    """
    全文搜索内容

    使用 PostgreSQL tsvector 进行全文搜索
    注意：默认 'simple' 配置对中文分词效果有限

    Args:
        session: 数据库会话
        query: 搜索关键词
        tenant_id: 租户 ID
        site_id: 站点 ID
        content_type: 可选，内容类型过滤
        limit: 返回结果数量限制

    Returns:
        匹配的内容列表，按相关度排序
    """
    # 构建搜索查询
    # 使用 plainto_tsquery 将用户输入转换为 tsquery
    # 使用 ts_rank 计算相关度
    stmt = (
        select(Content)
        .where(
            Content.tenant_id == tenant_id,
            Content.site_id == site_id,
            Content.deleted_at.is_(None),
            Content.status == "published",
            Content.search_vector.op("@@")(
                text("plainto_tsquery('simple', :query)")
            ),
        )
        .params(query=query)
        .order_by(
            text("ts_rank(search_vector, plainto_tsquery('simple', :query)) DESC")
        )
        .limit(limit)
    )

    if content_type:
        stmt = stmt.where(Content.content_type == content_type)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def search_contents_hybrid(
    session: AsyncSession,
    query: str,
    tenant_id: str,
    site_id: str,
    content_type: Optional[str] = None,
    limit: int = 20,
) -> List[Content]:
    """
    混合搜索：全文搜索 + LIKE 模糊匹配

    对于中文搜索，由于 tsvector 分词效果有限，
    同时使用 LIKE 进行模糊匹配以提高召回率

    Args:
        session: 数据库会话
        query: 搜索关键词
        tenant_id: 租户 ID
        site_id: 站点 ID
        content_type: 可选，内容类型过滤
        limit: 返回结果数量限制

    Returns:
        匹配的内容列表
    """
    like_pattern = f"%{query}%"

    stmt = (
        select(Content)
        .where(
            Content.tenant_id == tenant_id,
            Content.site_id == site_id,
            Content.deleted_at.is_(None),
            Content.status == "published",
            # 全文搜索 OR LIKE 模糊匹配
            (
                Content.search_vector.op("@@")(
                    text("plainto_tsquery('simple', :query)")
                )
                | Content.title.ilike(like_pattern)
                | Content.body.ilike(like_pattern)
            ),
        )
        .params(query=query)
        .order_by(Content.credibility_score.desc(), Content.created_at.desc())
        .limit(limit)
    )

    if content_type:
        stmt = stmt.where(Content.content_type == content_type)

    result = await session.execute(stmt)
    return list(result.scalars().all())


# ============================================================
# 中文全文搜索配置指南
# ============================================================
CHINESE_FTS_SETUP_GUIDE = """
# PostgreSQL 中文全文搜索配置指南

## 方案一：安装 zhparser 扩展（推荐）

```sql
-- 1. 安装 SCWS 分词库（需要系统权限）
-- Ubuntu/Debian:
-- apt-get install libscws-dev

-- 2. 安装 zhparser 扩展
CREATE EXTENSION zhparser;

-- 3. 创建中文搜索配置
CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
ALTER TEXT SEARCH CONFIGURATION chinese ADD MAPPING FOR n,v,a,i,e,l WITH simple;

-- 4. 更新 contents 表使用中文配置
ALTER TABLE contents
ALTER COLUMN search_vector TYPE tsvector
USING to_tsvector('chinese', COALESCE(title, '') || ' ' || COALESCE(body, ''));

-- 5. 更新触发器
CREATE OR REPLACE FUNCTION update_content_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('chinese', COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.body, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

## 方案二：使用 Qdrant 向量检索（生产推荐）

对于生产环境，建议使用 Qdrant 进行向量检索：

1. 使用 embedding 模型将内容向量化
2. 存储到 Qdrant 向量数据库
3. 查询时先向量检索，再从 PostgreSQL 获取完整内容

优势：
- 语义搜索，理解查询意图
- 支持相似度排序
- 更好的中文支持

参考配置：
- Qdrant 地址：QDRANT_URL
- Embedding 模型：text-embedding-3-small 或 bge-large-zh
"""
