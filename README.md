# 严田 AI 文明引擎 (Yantian AI Civilization Engine)

[![CI](https://github.com/your-org/yantian-ai-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/yantian-ai-platform/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> 祖宗智慧 × AI × 农耕节律 × 场景触发 × 游客行为学习

## 项目愿景

构建一个 **长期可演化的文化智能系统**，让徽派祖宗智慧在 AI 时代复活。

本项目 **不是**：

- ❌ 普通景区导览系统
- ❌ 单一 AI 聊天机器人
- ❌ 仅展示型数字内容

本项目 **是**：

- ✅ AI 导览 + AI NPC（祖先/匠人/农夫/塾师）
- ✅ 二十四节气智慧农耕引擎
- ✅ 研学任务系统
- ✅ 夜游与场景调度
- ✅ 后台 CMS 与运营中台
- ✅ 多村复制能力（多站点架构）

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| 后端语言 | Python 3.11+ |
| Web 框架 | FastAPI |
| 数据库 | PostgreSQL 15+ |
| 缓存 | Redis 7+ |
| 向量库 | Qdrant / Pinecone |
| 消息队列 | Celery + Redis |
| IoT | MQTT |
| AI 模型 | OpenAI / Qwen / Llama（抽象接口） |
| 前端 | Next.js 14 (Admin) / 微信小程序 |
| 容器化 | Docker + Docker Compose |
| CI/CD | GitHub Actions |

## 项目结构

```text
yantian-ai-platform/
├── services/           # 后端微服务
│   ├── core-backend/   # 主后端：鉴权、用户、内容、导览、场景触发
│   ├── ai-orchestrator/# AI编排层：NPC、RAG、提示词、护栏
│   ├── worker/         # 异步任务：向量化、媒体处理
│   ├── iot-gateway/    # IoT接入（Phase 2）
│   ├── farming-engine/ # 节气农耕引擎（Phase 2）
│   └── analytics/      # 游客画像分析（Phase 2）
├── apps/               # 前端应用
│   ├── admin-console/  # CMS/运营后台
│   ├── miniapp/        # 小程序/H5
│   └── kiosk/          # 现场触屏（可选）
├── packages/           # 共享包
│   ├── shared-schemas/ # JSON Schema 定义
│   └── sdk/            # 调用 SDK
├── data/               # 数据与知识库
│   ├── seeds/          # 初始化数据
│   ├── knowledge/      # 文化资料
│   └── prompts/        # 提示词版本化
├── docs/               # 文档
├── infra/              # 基础设施配置
├── scripts/            # 运维脚本
└── tests/              # 集成/E2E 测试
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- PostgreSQL 15+
- Redis 7+

### 本地开发

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/yantian-ai-platform.git
cd yantian-ai-platform

# 2. 复制环境变量
cp .env.example .env

# 3. 启动基础设施（数据库、Redis、向量库）
make infra-up

# 4. 初始化数据库
make db-init

# 5. 启动后端服务
make dev-backend

# 6. 启动 Admin 后台
make dev-admin
```

### Docker Compose 一键启动

```bash
docker-compose up -d
```

## 核心设计原则

1. **场景优先于算法** - 任何 AI/API/数据结构必须明确服务于哪个严田场景
2. **文化准确性高于智能表现** - 不允许编造徽派历史、祖训、农耕知识
3. **模块化、可拆解、可替换** - 每个能力都是独立模块
4. **内容可运营** - NPC人设、任务树、场景规则必须配置化
5. **人机协同** - AI 是祖宗智慧的解释器，不是篡改者

## 文档索引

- [系统架构](docs/01_architecture.md)
- [数据模型](docs/02_data_model.md)
- [API 规范](docs/03_api_spec.md)
- [NPC 人设规范](docs/04_npc_persona_spec.md)
- [场景触发规范](docs/05_scene_trigger_spec.md)
- [研学任务 Schema](docs/06_learning_quest_schema.md)
- [运维手册](docs/08_ops_runbook.md)

## 版本规划

| 版本 | 里程碑 | 状态 |
|------|--------|------|
| v0.1.0 | MVP：core-backend + ai-orchestrator + admin-console | ✅ 已完成 |
| v0.2.0 | 研学任务系统 + 游客画像 + 成就体系 | ✅ 已完成 |
| v0.3.0 | IoT 接入 + 节气农耕引擎 | ✅ 已完成 |
| v0.4.0 | AI 增强：智能推荐 + 个性化体验 | 📋 计划中 |
| v1.0.0 | 生产就绪 + 多站点支持 | 📋 计划中 |

### v0.3.0 更新内容 (2024-12-20)

**节气农耕引擎**
- 二十四节气数据模型与预置数据
- 农耕知识管理（CRUD、按节气/分类筛选）
- 当前节气 API（自动计算）

**IoT 设备管理**
- 设备注册与状态监控
- 设备心跳与日志记录
- 设备控制命令接口（预留）

**前端管理页面**
- 节气农耕展示页面
- 农耕知识管理页面
- IoT 设备管理页面

### v0.2.0 更新内容 (2024-12-19)

**研学任务系统**
- 任务定义与步骤管理
- 任务进度追踪
- 任务提交与审核

**游客画像系统**
- 游客档案管理
- 标签系统
- 打卡记录与 NPC 交互统计

**成就体系**
- 成就定义与规则引擎
- 自动解锁（计数型/事件型/组合型）
- 系统联动（任务完成/打卡触发成就检查）

## 贡献指南

请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)

## 许可证

[MIT License](LICENSE)

---

**严田 AI 文明引擎** - 让祖宗智慧在 AI 时代复活
