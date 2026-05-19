# How To Create A New Project

本文档说明如何从零新建一个与当前仓库组织方式一致的项目。它是给人和 AI agent 使用的项目初始化参考，不是当前项目的运行说明。

核心原则：

- 项目代码放在 `project/` 文件夹下。
- 项目开发文档放在 `dev_doc/` 文件夹下。
- 仓库根目录保留必要的工程入口文件，例如 `.git/`、`.vscode/`、`pyproject.toml`、启动脚本或 README。
- 文档体系按 `dev_doc/README.md` 的规则建立和维护。

## 推荐根目录结构

新项目建议从下面的结构开始：

```text
new_project/
  .git/
  .vscode/
  project/
  dev_doc/
  reference/
  pyproject.toml
  README.md
```

其中：

- `.git/` 是 Git 仓库目录，由 `git init` 或克隆仓库生成。
- `.vscode/` 保存项目级 IDE 配置，例如 Python 解释器、测试入口、格式化设置、常用任务。
- `project/` 保存实际代码。
- `dev_doc/` 保存当前项目的设计文档、prompt、术语表、未来任务、变更记录等。
- `reference/` 保存外部资料、旧项目材料、论文、调试经验、迁移参考等。
- `pyproject.toml` 保存 Python 项目的测试、路径、构建或工具配置。
- `README.md` 是面向用户或开发者的项目入口说明。

如果新项目不是 Python 项目，可以保留 `project/` 和 `dev_doc/` 的组织原则，同时将 `pyproject.toml` 换成对应语言的工程配置文件。

## 建立 Git 仓库

新项目应当有 `.git/`。推荐流程：

```powershell
mkdir new_project
cd new_project
git init
```

然后添加 `.gitignore`。至少忽略：

```text
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.pyc
.env
.venv/
venv/
build/
dist/
```

如果项目会产生大体积运行数据，还应忽略：

```text
project/jobs/
project/recorded_data/*.npz
project/surrogate/checkpoints/
project/test/_pytest_tmp/
```

忽略规则要根据项目性质调整。不要把必须复现实验或运行的源文件误加入 `.gitignore`。

## 建立 `.vscode/`

新项目应当有 `.vscode/`，用于保存团队共享的编辑器配置。常见文件包括：

```text
.vscode/
  settings.json
  launch.json
  tasks.json
```

建议 `settings.json` 至少说明：

- Python 测试框架。
- 默认格式化工具。
- 是否启用类型检查。
- 是否排除运行时目录和缓存目录。

示例：

```json
{
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "python.testing.pytestArgs": ["project/test"],
  "files.exclude": {
    "**/__pycache__": true,
    "**/.pytest_cache": true
  }
}
```

如果配置中包含本机绝对路径、个人账号、密钥或私有环境路径，不应提交进仓库。

## 建立 `project/`

`project/` 是代码根目录。所有可运行源代码、模块、测试和项目内工具都应放在这里，而不是散落在仓库根目录。

一个模块化项目可以从下面的结构开始：

```text
project/
  __init__.py
  config.py
  module_a/
    __init__.py
    api.py
  module_b/
    __init__.py
    api.py
  tools/
    __init__.py
  test/
```

推荐原则：

- 对外调用入口优先放在各模块的 `api.py`。
- 模块内部实现文件可以自由拆分，但跨核心模块调用应尽量走对方 `api.py`。
- `config.py` 只放跨模块共享的配置，不放强任务相关逻辑。
- `tools/` 放用户手动运行的辅助脚本，核心运行流程不要依赖它。
- `test/` 放默认测试，测试应尽量能在本地环境运行，不依赖昂贵外部软件。

如果项目含有运行时输出，应把输出目录放在 `project/` 下，例如：

```text
project/jobs/
project/output/
project/cache/
```

这些目录是否提交到 Git，取决于它们是源数据、样例数据，还是纯运行产物。

## 建立 `dev_doc/`

`dev_doc/` 是开发文档根目录。它的结构应与当前项目的 `dev_doc/README.md` 保持一致。

推荐结构：

```text
dev_doc/
  README.md
  spec 20260502.md
  terminology.md
  reference_map.md
  architecture/
    00_architecture_index.md
    c4_context.md
    c4_container.md
    c4_component.md
    4plus1_logical_view.md
    4plus1_process_view.md
    4plus1_development_view.md
    4plus1_physical_view.md
    4plus1_scenarios.md
  prompt/
    00_project.md
    99_notes.md
    10_modules/
      module_a.md
      module_b.md
      config.md
      tests.md
      tools.md
  toDo/
  change_records/
  obsolete/
```

如果项目初期还没有这么多模块，可以先建立空文件夹和少量核心文档，但应尽早补齐：

- `README.md`
- `spec 20260502.md`
- `terminology.md`
- `architecture/00_architecture_index.md`
- `prompt/00_project.md`
- `prompt/99_notes.md`

## `dev_doc/README.md` 的写法

`dev_doc/README.md` 是文档系统入口。它应说明：

- AI 收集项目上下文时应该读哪些文档。
- 哪些文档必须全文读。
- 哪些文档只按需读。
- 哪些文档默认不读。
- `toDo/` 中未来任务为何必须默认全文读。
- 每类文档的用途。
- 每类文档的推荐写法和结构。
- 修改代码后应该如何同步更新文档。

推荐结构：

```text
# dev_doc README

## Reading Guide
## Document Roles
### `spec 20260502.md`
### `architecture/`
### `prompt/`
### `reference_map.md`
### `terminology.md`
### `toDo/`
### `change_records/`
### `obsolete/`
## Maintenance Rules
```

默认读取规则建议与当前项目一致：

- `spec 20260502.md` 全文读取。
- `architecture/` 下所有文件全文读取。
- `reference_map.md` 全文读取。
- `terminology.md` 全文读取。
- `toDo/` 下所有 Markdown 文件全文读取，即使当前用户指令看起来与 pending task 无关。
- `prompt/` 先读取所有文件名，再按需读取相关文件全文。
- `change_records/` 默认不读取。
- `obsolete/` 默认不读取。

## `spec 20260502.md` 的写法

`spec 20260502.md` 是最高层需求和设计契约。它不是流水账，也不是某个文件的注释。

中心思想：

- 说明项目必须具备什么能力。
- 说明哪些设计约束不能为了实现方便而牺牲。
- 说明模块边界和数据保存原则。
- 说明错误恢复、扩展性、长期维护等要求。

推荐结构：

```text
# Project Specification

## Background
## Goals
## Terminology
## Target Structure
## Module Responsibilities
## Communication Contracts
## Data Persistence Rules
## Error And Recovery Requirements
## Extension Requirements
## Core Invariants
```

`spec 20260502.md` 应该稳定。日常小改动不一定更新 spec，只有项目目标、核心约束、模块边界或长期设计原则变化时才更新。

## `architecture/` 的写法

`architecture/` 描述当前系统结构。它回答“现在这个系统怎么组织、怎么运行、边界在哪里”。

中心思想：

- 架构文档是当前视图，不是历史记录。
- 应强调模块关系、运行流程、部署位置、开发边界和不变量。
- 不应写成源码逐行解释。

推荐文件：

```text
00_architecture_index.md
c4_context.md
c4_container.md
c4_component.md
4plus1_logical_view.md
4plus1_process_view.md
4plus1_development_view.md
4plus1_physical_view.md
4plus1_scenarios.md
```

推荐段落结构：

```text
# View Name

## Scope
## Diagram Or Structure
## Responsibilities
## Rules / Invariants
## Notes
```

什么时候更新：

- 模块职责变化。
- 公共 API 或跨模块依赖变化。
- 数据流、持久化方式、运行流程变化。
- 部署方式或运行目录变化。
- 文档维护流程本身变化。

## `prompt/` 的写法

`prompt/` 是给 AI agent 使用的生成式模块说明。

中心思想：

> prompt 的目标是让 AI 能够根据这个文件从零开始生成一个同样功能的模块，而不是描述当前文件里每一行代码。

因此 prompt 应写：

- 模块为什么存在。
- 模块必须提供什么功能。
- 输入输出是什么形状。
- 哪些技巧容易被重写时丢失。
- 哪些部分经常变化，哪些合同应保持稳定。

推荐结构：

```text
# Module prompt: module_name

## Intent
- Why this module exists.

## Functionalities
- What this module must provide.

## I/O Format
- Public data shapes, files, APIs, and return values.

## Non-Obvious Techniques
- Important implementation ideas that should survive rewrites.

## Mutability Profile
- Which parts may change often and which contracts should stay stable.
```

推荐先写模块级 prompt，不要过早给每个源文件都写一个 prompt。文件级 prompt 只有在某个文件有复杂、稳定、容易误解的合同时才需要。

AI 收集信息时，应先列出 `prompt/` 所有文件名，然后根据任务选择相关文件全文读取。

## `toDo/` 的写法

`toDo/` 保存未来会做、但还没有完成的任务说明。一个 Markdown 文件可以描述一件事，也可以描述一组相关事项。

这个目录和 `change_records/` 的区别是：

- `toDo/` 描述未来目标，默认全文读取。
- `change_records/` 描述已经完成的重要变化，默认不读取。
- `obsolete/` 保存已经归档的旧计划、旧诊断和完成后的 toDo handoff，默认不读取。

文件名格式应和 `change_records/` 类似：

```text
YYYYMMDD_HHMMSS_short-description.md
```

示例：

```text
20260519_193400_nsga3-surrogate-handoff.md
20260602_143000_surrogate-cache-policy.md
```

AI 第一次读取 `dev_doc/` 时，应读取 `toDo/` 下所有 Markdown 文件全文，即使用户当前指令看起来和这些未来任务无关。目的不是马上执行所有 toDo，而是在执行当前任务时选择更能照顾未来目标的技术路线。

如果用户要求 AI 执行 `toDo/` 中的某个任务，AI 应在完成代码和文档更新后，将对应 Markdown 文件移动到 `obsolete/`。如果只完成了一部分，应保留或拆分剩余 toDo，再归档已完成的那一份。

## `reference_map.md` 的写法

`reference_map.md` 说明当前项目各模块和 `reference/` 里的旧材料有什么关系。

中心思想：

- 它不是复制计划。
- 它是索引和血缘说明。
- 它帮助 AI 快速找到最相关的旧代码、旧 prompt、论文或调试记录。

推荐结构：

```text
# Reference Map

## `project/` as a whole

Closest reference files:
- ...

Natural-language mapping:
- ...

## `project/module_name`

Closest reference files:
- ...

Natural-language mapping:
- ...

Current implementation note:
- ...
```

什么时候更新：

- 从旧项目复制或改写了重要实现。
- 某个模块的主要参考来源发生变化。
- 新增了重要外部参考资料。
- 发现旧 reference 不再适合作为当前模块参考。

## `terminology.md` 的写法

`terminology.md` 只记录项目特有、容易误解、或普通软件语境下含义不够精确的词。

中心思想：

- 术语表不是普通词典。
- 不需要解释大家都懂的技术词。
- 重点解释本项目中某个词的边界。

推荐结构：

```text
# Project-Specific Terminology

Only terms that need project context are listed here.

| Term | Meaning In This Project |
|---|---|
| `term` | Definition and boundary notes. |
```

什么时候更新：

- 某次修改发现之前对概念理解有误。
- 新增了名字不直观的概念。
- 某个词在代码、文档、历史项目中有多个可能含义。
- AI 或人容易把某个派生数据误认为持久数据。

## `change_records/` 的写法

`change_records/` 用来记录每次重要改动“改了什么、为什么改”。它类似 Architecture Decision Record，但范围更宽，可以记录架构决策、代码行为变化、文档治理变化、测试策略变化。

这个目录默认不读取。只有在需要追溯历史原因、处理冲突、或用户要求查看历史时才读取。

文件名格式：

```text
YYYYMMDD_HHMMSS_short-description.md
```

示例：

```text
20260518_075810_dev-doc-governance.md
20260602_143000-surrogate-cache-policy.md
```

推荐内容结构：

```text
# YYYY-MM-DD HH:MM - Short Title

## Context
- What situation or problem triggered the change.

## Change
- What was changed.

## Rationale
- Why this approach was chosen.

## Impact
- Which modules, docs, tests, or workflows are affected.

## Follow-Up
- Optional remaining work, risks, or things to revisit.
```

建议每次代码修改后都添加一条 change record。纯文档修改如果改变了文档体系、维护规则、重要说明，也应该添加一条记录。

## `obsolete/` 的写法

`obsolete/` 保存已经不作为当前设计依据的旧计划、旧诊断、旧草案，以及已经完成并归档的 toDo handoff。

原则：

- 默认不读。
- 不作为当前事实来源。
- 可以在调查历史原因时读取。
- 不要删除仍可能帮助理解历史背景的旧材料。

如果某个 obsolete 文档重新变成当前设计依据，应把相关内容迁移到 `spec 20260502.md`、`architecture/`、`prompt/` 或 `reference_map.md`，而不是直接把 obsolete 当作当前文档使用。

## 建立 `reference/`

`reference/` 保存项目外部或历史参考资料。它不同于 `dev_doc/`：

- `dev_doc/` 是当前项目文档。
- `reference/` 是参考来源、旧项目、论文、调试记录、迁移指南。

可以放入：

```text
reference/
  old_project_a/
  old_project_b/
  paper_or_algorithm_reference.tex
  htcondor_debug_reference.md
  how_to_create_new_project.md
```

`reference/` 下的内容不应默认全文读取。应通过 `dev_doc/reference_map.md` 或用户明确要求来决定读取哪些参考资料。

## 新项目初始化步骤

推荐顺序：

1. 创建根目录。
2. 执行 `git init`，生成 `.git/`。
3. 创建 `.gitignore`。
4. 创建 `.vscode/` 和基础编辑器配置。
5. 创建 `project/`，放入最小可 import 的代码结构。
6. 创建 `dev_doc/`，先写 `README.md`、`spec 20260502.md`、`terminology.md`、`architecture/00_architecture_index.md`、`prompt/00_project.md`，并建立空的 `toDo/`、`change_records/`、`obsolete/` 文件夹。
7. 创建 `reference/`，放入外部材料或旧项目参考。
8. 添加最小测试入口，例如 `project/test/` 和 `pyproject.toml`。
9. 跑一次最小测试或 import 检查。
10. 第一次 commit。

## 最小可用项目骨架

一个最小 Python 项目可以是：

```text
new_project/
  .git/
  .gitignore
  .vscode/
    settings.json
  pyproject.toml
  README.md
  project/
    __init__.py
    config.py
    api.py
    test/
      test_import.py
  dev_doc/
    README.md
    spec 20260502.md
    terminology.md
    reference_map.md
    architecture/
      00_architecture_index.md
    prompt/
      00_project.md
      99_notes.md
      10_modules/
        project.md
        config.md
        tests.md
    toDo/
    change_records/
    obsolete/
  reference/
```

`project/test/test_import.py` 可以先只检查项目能 import：

```python
def test_project_imports():
    import project

    assert project is not None
```

## AI Agent 新建项目时的注意事项

AI agent 新建项目时，应遵守以下规则：

- 不要把代码直接散放在根目录。
- 不要把当前设计文档和历史参考资料混在一起。
- 不要跳过 `toDo/`；第一次读取 `dev_doc/` 时应读取其中所有 Markdown 文件全文。
- 不要把 `change_records/` 当作默认上下文来源。
- 不要把 prompt 写成当前代码摘要，要写成可重建模块功能的生成式说明。
- 不要把架构文档写成代码逐行讲解，要写系统边界、数据流和不变量。
- 不要在 `.vscode/` 中提交个人机器路径、密钥或私有配置。
- 不要把运行时大文件、缓存、临时输出误提交。

AI agent 修改代码后，应：

1. 根据影响范围更新 `dev_doc/architecture/`。
2. 根据模块行为更新 `dev_doc/prompt/`。
3. 如有概念修正或新术语，更新 `dev_doc/terminology.md`。
4. 添加 `dev_doc/change_records/YYYYMMDD_HHMMSS_short-description.md`。
5. 如果完成了 `dev_doc/toDo/` 中的任务，将对应 Markdown 文件移动到 `dev_doc/obsolete/`。
6. 运行合适的测试。
7. 在最终回复中说明改动和验证结果。

## 判断一个新项目是否结构健康

可以用下面的检查表：

- 根目录是否简洁，只保留工程入口和顶层目录？
- 实际代码是否都在 `project/` 下？
- 开发文档是否都在 `dev_doc/` 下？
- `dev_doc/README.md` 是否说明了读取顺序和写法？
- `architecture/` 是否描述当前系统，而不是旧计划？
- `prompt/` 是否能指导 AI 重建模块功能？
- `terminology.md` 是否解释了项目特有概念？
- `toDo/` 是否用于保存未来未完成事项，且默认全文读取？
- `change_records/` 是否用于记录重要变更原因，且默认不读？
- `reference/` 是否只保存参考资料，而不是当前项目事实来源？
- 是否有 `.git/`、`.gitignore`、`.vscode/`？
- 是否有最小测试或最小 import 检查？

满足这些条件后，新项目通常就具备了比较清楚的代码、文档和历史演进边界。
