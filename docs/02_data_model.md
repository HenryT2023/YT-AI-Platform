# 数据模型

## 1. 概述

本文档定义严田 AI 文明引擎的核心数据模型。所有实体设计遵循以下原则：

- **多站点支持**: 核心实体带 `site_id` 字段
- **软删除**: 使用 `deleted_at` 而非物理删除
- **审计追踪**: 记录 `created_at`, `updated_at`, `created_by`
- **配置化**: 复杂配置使用 JSONB 存储

## 2. ER 图

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│    Site     │───┬──►│   Scene     │───┬──►│     POI     │
│  (站点)     │   │   │   (场景)    │   │   │  (兴趣点)   │
└─────────────┘   │   └─────────────┘   │   └─────────────┘
                  │                     │
                  │   ┌─────────────┐   │   ┌─────────────┐
                  ├──►│    NPC      │   └──►│   Asset     │
                  │   │  (虚拟人物) │       │  (媒体资源) │
                  │   └─────────────┘       └─────────────┘
                  │
                  │   ┌─────────────┐       ┌─────────────┐
                  ├──►│   Quest     │──────►│  QuestStep  │
                  │   │  (研学任务) │       │  (任务步骤) │
                  │   └─────────────┘       └─────────────┘
                  │
                  │   ┌─────────────┐       ┌─────────────┐
                  ├──►│SceneTrigger │       │   Device    │
                  │   │ (场景触发)  │       │  (IoT设备)  │
                  │   └─────────────┘       └─────────────┘
                  │
                  │   ┌─────────────┐       ┌─────────────┐
                  └──►│   Visitor   │──────►│VisitorQuest │
                      │  (游客档案) │       │(任务进度)   │
                      └─────────────┘       └─────────────┘
```

## 3. 核心实体

### 3.1 Site（站点）

```sql
CREATE TABLE sites (
    id VARCHAR(50) PRIMARY KEY,           -- 如 "yantian-main"
    name VARCHAR(100) NOT NULL,           -- 站点名称
    display_name VARCHAR(200),            -- 展示名称
    description TEXT,                     -- 站点描述
    
    -- 站点配置
    config JSONB DEFAULT '{}',            -- 站点级配置
    theme JSONB DEFAULT '{}',             -- 主题配置（颜色、Logo等）
    
    -- 地理信息
    location_lat DECIMAL(10, 8),          -- 纬度
    location_lng DECIMAL(11, 8),          -- 经度
    timezone VARCHAR(50) DEFAULT 'Asia/Shanghai',
    
    -- 状态
    status VARCHAR(20) DEFAULT 'active',  -- active / inactive / maintenance
    
    -- 审计字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE
);
```

**config 字段示例**:

```json
{
  "features": {
    "ai_guide": true,
    "night_tour": false,
    "farming_engine": true
  },
  "llm": {
    "provider": "openai",
    "model": "gpt-4o"
  },
  "limits": {
    "max_daily_ai_calls": 10000
  }
}
```

### 3.2 Scene（场景）

```sql
CREATE TABLE scenes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id VARCHAR(50) NOT NULL REFERENCES sites(id),
    
    -- 基本信息
    name VARCHAR(100) NOT NULL,
    display_name VARCHAR(200),
    description TEXT,
    scene_type VARCHAR(50),               -- building / garden / path / water / ...
    
    -- 空间信息
    location_lat DECIMAL(10, 8),
    location_lng DECIMAL(11, 8),
    boundary JSONB,                       -- GeoJSON 边界
    floor_plan_asset_id UUID,             -- 平面图资源
    
    -- 场景配置
    config JSONB DEFAULT '{}',
    
    -- 关联
    parent_scene_id UUID REFERENCES scenes(id),  -- 父场景（层级结构）
    
    -- 排序与状态
    sort_order INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    
    -- 审计字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_scenes_site_id ON scenes(site_id);
```

### 3.3 POI（兴趣点）

```sql
CREATE TABLE pois (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id VARCHAR(50) NOT NULL REFERENCES sites(id),
    scene_id UUID REFERENCES scenes(id),
    
    -- 基本信息
    name VARCHAR(100) NOT NULL,
    display_name VARCHAR(200),
    description TEXT,
    poi_type VARCHAR(50),                 -- artifact / inscription / tree / well / ...
    
    -- 位置
    location_lat DECIMAL(10, 8),
    location_lng DECIMAL(11, 8),
    indoor_position JSONB,                -- 室内定位坐标
    
    -- 内容
    content JSONB DEFAULT '{}',           -- 富文本内容、多语言
    
    -- 关联媒体
    cover_asset_id UUID,
    audio_guide_asset_id UUID,
    
    -- 元数据
    tags VARCHAR(50)[],
    metadata JSONB DEFAULT '{}',
    
    -- 排序与状态
    sort_order INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    
    -- 审计字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_pois_site_id ON pois(site_id);
CREATE INDEX idx_pois_scene_id ON pois(scene_id);
```

### 3.4 NPC（虚拟人物）

```sql
CREATE TABLE npcs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id VARCHAR(50) NOT NULL REFERENCES sites(id),
    
    -- 基本信息
    name VARCHAR(100) NOT NULL,           -- 内部名称
    display_name VARCHAR(200),            -- 展示名称（如"严氏先祖"）
    npc_type VARCHAR(50),                 -- ancestor / craftsman / farmer / teacher / ...
    
    -- 人设配置（核心）
    persona JSONB NOT NULL,               -- 详细人设，见下方 Schema
    
    -- 形象资源
    avatar_asset_id UUID,
    voice_id VARCHAR(100),                -- TTS 音色 ID
    
    -- 关联场景（NPC 可出现在哪些场景）
    scene_ids UUID[],
    
    -- 对话配置
    greeting_templates TEXT[],            -- 问候语模板
    fallback_responses TEXT[],            -- 兜底回复
    
    -- 状态
    status VARCHAR(20) DEFAULT 'active',
    
    -- 审计字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_npcs_site_id ON npcs(site_id);
```

**persona 字段 Schema**（详见 [04_npc_persona_spec.md](04_npc_persona_spec.md)）:

```json
{
  "identity": {
    "era": "清朝乾隆年间",
    "role": "严氏第十八代族长",
    "background": "..."
  },
  "personality": {
    "traits": ["睿智", "严谨", "慈祥"],
    "speaking_style": "文言与白话混用，常引用祖训"
  },
  "knowledge_domains": ["家族历史", "祖训家规", "徽商文化"],
  "constraints": {
    "forbidden_topics": ["政治敏感", "宗教争议"],
    "must_cite_sources": true
  }
}
```

### 3.5 Quest（研学任务）

```sql
CREATE TABLE quests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id VARCHAR(50) NOT NULL REFERENCES sites(id),
    
    -- 基本信息
    name VARCHAR(100) NOT NULL,
    display_name VARCHAR(200),
    description TEXT,
    quest_type VARCHAR(50),               -- exploration / learning / challenge / ...
    
    -- 任务配置
    config JSONB NOT NULL,                -- 任务详细配置
    
    -- 奖励
    rewards JSONB DEFAULT '{}',           -- 积分、徽章、解锁内容
    
    -- 前置条件
    prerequisites JSONB DEFAULT '{}',     -- 前置任务、等级要求
    
    -- 时间限制
    available_from TIMESTAMP WITH TIME ZONE,
    available_until TIMESTAMP WITH TIME ZONE,
    time_limit_minutes INT,               -- 任务时限
    
    -- 关联场景
    scene_ids UUID[],
    
    -- 难度与分类
    difficulty VARCHAR(20),               -- easy / medium / hard
    category VARCHAR(50),
    tags VARCHAR(50)[],
    
    -- 排序与状态
    sort_order INT DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active',
    
    -- 审计字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_quests_site_id ON quests(site_id);
```

### 3.6 QuestStep（任务步骤）

```sql
CREATE TABLE quest_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quest_id UUID NOT NULL REFERENCES quests(id),
    
    -- 步骤信息
    step_number INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    step_type VARCHAR(50),                -- visit / answer / scan / collect / ...
    
    -- 步骤配置
    config JSONB NOT NULL,                -- 步骤详细配置
    
    -- 关联
    poi_id UUID REFERENCES pois(id),
    npc_id UUID REFERENCES npcs(id),
    
    -- 验证规则
    validation_rules JSONB DEFAULT '{}',
    
    -- 提示
    hints TEXT[],
    
    -- 状态
    status VARCHAR(20) DEFAULT 'active',
    
    -- 审计字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_quest_steps_quest_id ON quest_steps(quest_id);
```

### 3.7 Asset（媒体资源）

```sql
CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id VARCHAR(50) NOT NULL REFERENCES sites(id),
    
    -- 基本信息
    name VARCHAR(200) NOT NULL,
    asset_type VARCHAR(50) NOT NULL,      -- image / audio / video / document / 3d_model
    mime_type VARCHAR(100),
    
    -- 存储信息
    storage_provider VARCHAR(50),         -- s3 / oss / local
    storage_path VARCHAR(500) NOT NULL,
    storage_url VARCHAR(1000),
    file_size BIGINT,
    
    -- 媒体元数据
    metadata JSONB DEFAULT '{}',          -- 宽高、时长、格式等
    
    -- 处理状态
    processing_status VARCHAR(20),        -- pending / processing / completed / failed
    variants JSONB DEFAULT '{}',          -- 缩略图、不同分辨率版本
    
    -- 分类
    category VARCHAR(50),
    tags VARCHAR(50)[],
    
    -- 审计字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_assets_site_id ON assets(site_id);
CREATE INDEX idx_assets_asset_type ON assets(asset_type);
```

### 3.8 SceneTrigger（场景触发规则）

```sql
CREATE TABLE scene_triggers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id VARCHAR(50) NOT NULL REFERENCES sites(id),
    scene_id UUID REFERENCES scenes(id),
    
    -- 基本信息
    name VARCHAR(100) NOT NULL,
    description TEXT,
    trigger_type VARCHAR(50),             -- time / location / event / sensor / manual
    
    -- 触发条件
    conditions JSONB NOT NULL,            -- 触发条件配置
    
    -- 触发动作
    actions JSONB NOT NULL,               -- 触发后执行的动作
    
    -- 优先级与冲突处理
    priority INT DEFAULT 0,
    conflict_group VARCHAR(50),           -- 同组规则互斥
    
    -- 生效时间
    active_from TIMESTAMP WITH TIME ZONE,
    active_until TIMESTAMP WITH TIME ZONE,
    active_time_ranges JSONB,             -- 每日生效时段
    
    -- 状态
    status VARCHAR(20) DEFAULT 'active',
    
    -- 审计字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_scene_triggers_site_id ON scene_triggers(site_id);
CREATE INDEX idx_scene_triggers_scene_id ON scene_triggers(scene_id);
```

### 3.9 Visitor（游客档案）

```sql
CREATE TABLE visitors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- 身份信息
    external_id VARCHAR(200),             -- 微信 OpenID 等
    identity_provider VARCHAR(50),        -- wechat / alipay / phone
    
    -- 基本信息
    nickname VARCHAR(100),
    avatar_url VARCHAR(500),
    phone VARCHAR(20),
    
    -- 画像数据
    profile JSONB DEFAULT '{}',           -- 兴趣标签、偏好等
    
    -- 统计数据
    stats JSONB DEFAULT '{}',             -- 访问次数、完成任务数等
    
    -- 审计字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_visit_at TIMESTAMP WITH TIME ZONE
);

CREATE UNIQUE INDEX idx_visitors_external_id ON visitors(external_id, identity_provider);
```

### 3.10 VisitorQuest（游客任务进度）

```sql
CREATE TABLE visitor_quests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    visitor_id UUID NOT NULL REFERENCES visitors(id),
    quest_id UUID NOT NULL REFERENCES quests(id),
    
    -- 进度
    status VARCHAR(20) DEFAULT 'in_progress',  -- in_progress / completed / abandoned
    current_step INT DEFAULT 1,
    progress JSONB DEFAULT '{}',          -- 各步骤完成情况
    
    -- 时间
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- 得分与奖励
    score INT DEFAULT 0,
    rewards_claimed JSONB DEFAULT '{}',
    
    UNIQUE(visitor_id, quest_id)
);

CREATE INDEX idx_visitor_quests_visitor_id ON visitor_quests(visitor_id);
CREATE INDEX idx_visitor_quests_quest_id ON visitor_quests(quest_id);
```

## 4. 知识库实体

### 4.1 KnowledgeDocument（知识文档）

```sql
CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id VARCHAR(50) NOT NULL REFERENCES sites(id),
    
    -- 基本信息
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    doc_type VARCHAR(50),                 -- history / folklore / craft / farming / ...
    
    -- 来源与可信度
    source VARCHAR(200),                  -- 来源（书籍、口述、档案）
    source_url VARCHAR(500),
    credibility VARCHAR(20),              -- verified / unverified / legend
    
    -- 向量化状态
    embedding_status VARCHAR(20),         -- pending / completed / failed
    embedding_model VARCHAR(100),
    chunk_count INT DEFAULT 0,
    
    -- 分类
    category VARCHAR(50),
    tags VARCHAR(50)[],
    
    -- 审计字段
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID,
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_knowledge_documents_site_id ON knowledge_documents(site_id);
```

## 5. 事件与日志

### 5.1 EventLog（事件日志）

```sql
CREATE TABLE event_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id VARCHAR(50),
    
    -- 事件信息
    event_type VARCHAR(50) NOT NULL,      -- visitor_enter / npc_chat / quest_complete / ...
    event_data JSONB NOT NULL,
    
    -- 关联实体
    visitor_id UUID,
    scene_id UUID,
    npc_id UUID,
    quest_id UUID,
    
    -- 时间
    occurred_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- 设备信息
    device_info JSONB
);

-- 使用 TimescaleDB 或分区表优化时序查询
CREATE INDEX idx_event_logs_occurred_at ON event_logs(occurred_at DESC);
CREATE INDEX idx_event_logs_event_type ON event_logs(event_type);
CREATE INDEX idx_event_logs_visitor_id ON event_logs(visitor_id);
```

## 6. 索引策略

### 6.1 常用查询索引

```sql
-- 站点内场景列表
CREATE INDEX idx_scenes_site_status ON scenes(site_id, status) WHERE deleted_at IS NULL;

-- 场景内 POI 列表
CREATE INDEX idx_pois_scene_status ON pois(scene_id, status) WHERE deleted_at IS NULL;

-- 活跃任务列表
CREATE INDEX idx_quests_active ON quests(site_id, status, available_from, available_until) 
    WHERE deleted_at IS NULL;

-- 游客任务进度
CREATE INDEX idx_visitor_quests_status ON visitor_quests(visitor_id, status);
```

### 6.2 全文搜索

```sql
-- POI 全文搜索
ALTER TABLE pois ADD COLUMN search_vector tsvector;
CREATE INDEX idx_pois_search ON pois USING GIN(search_vector);

-- 知识文档全文搜索
ALTER TABLE knowledge_documents ADD COLUMN search_vector tsvector;
CREATE INDEX idx_knowledge_search ON knowledge_documents USING GIN(search_vector);
```

## 7. 迁移策略

使用 Alembic 管理数据库迁移：

```bash
# 生成迁移
alembic revision --autogenerate -m "add_new_field"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```
