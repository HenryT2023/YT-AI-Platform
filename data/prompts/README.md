# Prompt 资产目录

## 概述

本目录存放 NPC Prompt 的初始化文件和备份。

**真源（Source of Truth）：数据库**

- 运营后台通过 API 管理 Prompt 版本
- 本目录作为初始化种子和备份
- 导入脚本：`scripts/import_prompts.py`

## 目录结构

```text
data/prompts/
├── README.md                 # 本文件
├── ancestor_yan.yaml         # 严氏先祖 Prompt
├── craftsman_wang.yaml       # 王家匠人 Prompt
├── farmer_li.yaml            # 李家农夫 Prompt
└── _template.yaml            # 模板文件
```

## 文件格式

每个 Prompt 文件使用 YAML 格式，包含：

```yaml
# 元数据
meta:
  npc_id: ancestor_yan        # NPC ID（必需）
  version: 1                  # 版本号（必需）
  name: 严氏先祖              # 显示名称
  author: system              # 作者
  created_at: 2024-12-13      # 创建时间
  description: 严氏先祖系统提示词 v1

# 策略配置
policy:
  require_citations: true     # 是否要求引用
  min_confidence: 0.5         # 最低置信度
  forbidden_topics:           # 禁止话题
    - 政治敏感
    - 宗教争议
  max_response_length: 500    # 最大回复长度

# Prompt 正文
prompt: |
  你是严氏先祖...
```

## 导入命令

```bash
# 导入所有 Prompt
python scripts/import_prompts.py

# 导入指定文件
python scripts/import_prompts.py --file ancestor_yan.yaml

# 强制覆盖已存在版本
python scripts/import_prompts.py --force
```

## 版本管理

- 每次修改创建新版本，不覆盖旧版本
- 通过 API 设置 active 版本
- 支持回滚到历史版本
