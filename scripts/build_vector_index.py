#!/usr/bin/env python3
"""
向量索引构建脚本

将知识库文档向量化并存入 Qdrant
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "worker"))

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

from app.config import settings


def create_collection():
    """创建 Qdrant collection"""
    client = QdrantClient(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        api_key=settings.QDRANT_API_KEY,
    )

    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if settings.QDRANT_COLLECTION in collection_names:
        print(f"⚠️ Collection '{settings.QDRANT_COLLECTION}' already exists")
        return

    client.create_collection(
        collection_name=settings.QDRANT_COLLECTION,
        vectors_config=VectorParams(
            size=1536,  # text-embedding-3-small 维度
            distance=Distance.COSINE,
        ),
    )
    print(f"✅ Collection '{settings.QDRANT_COLLECTION}' created")


def main():
    """主函数"""
    print("🔢 Building vector index...")
    create_collection()
    print("✅ Vector index ready")


if __name__ == "__main__":
    main()
