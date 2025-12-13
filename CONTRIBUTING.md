# 贡献指南 (Contributing Guide)

感谢你对 **严田 AI 文明引擎** 项目的关注！本文档描述了参与项目开发的规范和流程。

## 目录

- [开发环境设置](#开发环境设置)
- [Git 工作流](#git-工作流)
- [分支命名规范](#分支命名规范)
- [Commit 提交规范](#commit-提交规范)
- [代码规范](#代码规范)
- [Pull Request 流程](#pull-request-流程)
- [代码审查](#代码审查)

---

## 开发环境设置

### 前置要求

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- Git 2.30+

### 本地开发环境

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/your-username/yantian-ai-platform.git
cd yantian-ai-platform

# 2. 添加上游仓库
git remote add upstream https://github.com/your-org/yantian-ai-platform.git

# 3. 复制环境变量
cp .env.example .env

# 4. 启动基础设施
make infra-up

# 5. 安装 Python 依赖（以 core-backend 为例）
cd services/core-backend
pip install -e ".[dev]"

# 6. 运行测试确保环境正常
pytest
```

---

## Git 工作流

本项目采用 **GitHub Flow** 工作流：

1. 从 `main` 分支创建功能分支
2. 在功能分支上开发并提交
3. 创建 Pull Request 请求合并到 `main`
4. 代码审查通过后合并
5. 删除功能分支

### 保持分支同步

```bash
# 获取上游最新代码
git fetch upstream

# 将 main 分支与上游同步
git checkout main
git merge upstream/main

# 变基你的功能分支
git checkout feature/your-feature
git rebase main
```

---

## 分支命名规范

分支名称格式：`<type>/<short-description>`

| 类型 | 说明 | 示例 |
|------|------|------|
| `feature/` | 新功能 | `feature/npc-dialogue` |
| `fix/` | Bug 修复 | `fix/auth-token-expire` |
| `refactor/` | 代码重构 | `refactor/db-session` |
| `docs/` | 文档更新 | `docs/api-spec` |
| `test/` | 测试相关 | `test/guardrail-unit` |
| `chore/` | 构建/工具 | `chore/ci-workflow` |

**命名规则**：

- 使用小写字母和连字符 `-`
- 简短但有描述性
- 避免使用中文

---

## Commit 提交规范

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范。

### 提交格式

```text
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Type 类型

| 类型 | 说明 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `docs` | 文档变更 |
| `style` | 代码格式（不影响功能） |
| `refactor` | 代码重构（不是新功能也不是修复） |
| `perf` | 性能优化 |
| `test` | 添加或修改测试 |
| `chore` | 构建过程或辅助工具变动 |
| `ci` | CI 配置变更 |
| `revert` | 回滚提交 |

### Scope 范围（可选）

- `core-backend` - 主后端服务
- `ai-orchestrator` - AI 编排服务
- `worker` - 异步任务服务
- `admin` - 运营后台
- `schema` - JSON Schema
- `docs` - 文档
- `ci` - CI/CD
- `deps` - 依赖更新

### 示例

```bash
# 新功能
feat(core-backend): add NPC CRUD API endpoints

# Bug 修复
fix(ai-orchestrator): fix session memory TTL not applied

# 文档
docs: update README with quick start guide

# 重构
refactor(core-backend): extract auth logic to separate module

# 带 Breaking Change
feat(api)!: change /api/v1/chat request format

BREAKING CHANGE: request body now requires `npc_persona` field
```

### Commit 最佳实践

1. **原子提交** - 每个 commit 只做一件事
2. **有意义的消息** - 说明「做了什么」和「为什么」
3. **不要提交** - `.env`、`__pycache__`、`node_modules` 等
4. **提交前检查** - 运行 `make lint` 和 `make test`

---

## 代码规范

### Python 代码规范

- 遵循 [PEP 8](https://peps.python.org/pep-0008/)
- 使用 [Ruff](https://github.com/astral-sh/ruff) 进行 lint
- 行宽限制：100 字符
- 类型注解：所有公开函数必须有类型注解

```bash
# 运行 lint
make lint

# 自动格式化
make format
```

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件名 | snake_case | `npc_service.py` |
| 类名 | PascalCase | `NPCOrchestrator` |
| 函数/变量 | snake_case | `get_npc_by_id` |
| 常量 | UPPER_SNAKE_CASE | `MAX_RESPONSE_TOKENS` |
| API 路由 | kebab-case | `/api/v1/npc-personas` |

### 文档规范

- 所有公开 API 必须有 docstring
- 使用 Google 风格的 docstring
- 复杂逻辑需要注释说明「为什么」

---

## Pull Request 流程

### 创建 PR 前

1. 确保代码通过所有测试：`make test`
2. 确保代码通过 lint：`make lint`
3. 更新相关文档
4. 变基到最新的 `main` 分支

### PR 标题格式

与 Commit 格式一致：

```text
feat(core-backend): add visitor quest progress API
```

### PR 描述模板

```markdown
## 变更说明

简要描述这个 PR 做了什么。

## 变更类型

- [ ] 新功能 (feat)
- [ ] Bug 修复 (fix)
- [ ] 重构 (refactor)
- [ ] 文档 (docs)
- [ ] 测试 (test)
- [ ] 其他

## 相关 Issue

Closes #123

## 测试说明

描述如何测试这些变更。

## 截图（如适用）

## Checklist

- [ ] 代码通过 lint
- [ ] 添加/更新了测试
- [ ] 更新了相关文档
- [ ] 本地测试通过
```

---

## 代码审查

### 审查重点

1. **功能正确性** - 代码是否实现了预期功能
2. **代码质量** - 是否遵循项目规范
3. **安全性** - 是否有安全隐患
4. **性能** - 是否有性能问题
5. **可维护性** - 代码是否易于理解和维护

### 审查礼仪

- 保持建设性和尊重
- 解释「为什么」而不只是「什么」
- 区分「必须修改」和「建议修改」
- 及时响应审查意见

---

## 发布流程

版本号遵循 [Semantic Versioning](https://semver.org/)：

- **MAJOR** - 不兼容的 API 变更
- **MINOR** - 向后兼容的新功能
- **PATCH** - 向后兼容的 Bug 修复

---

## 联系方式

如有问题，请通过以下方式联系：

- GitHub Issues
- 项目讨论区

---

感谢你的贡献！🙏
