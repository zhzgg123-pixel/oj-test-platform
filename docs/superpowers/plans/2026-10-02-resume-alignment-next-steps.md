# OJ 平台简历对齐：后续分步实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 executing-plans 按任务实施。每次完成一个可验收的提交；未经用户选择，不自行启用多代理。

**Goal:** 让简历能力逐项具备实现、测试和运行证据，并分步同步到 Gitee。

**Architecture:** 保留 FastAPI、静态前端、Adapter、生成器和执行器。Web/CLI 共用 TaskService，SQLite 保存实际输入及结果，报告从持久化快照生成；Mock 与真实 C++ OJ 分层验收。

**Tech Stack:** Python、FastAPI、Pydantic、SQLite、pytest、线程池、Docker Compose、GitHub Actions。

**Spec:** [设计与验收约定](../../design-contract.md)。完整文件清单、接口、测试示例及各阶段操作见 [S00–S12 实施计划](../../implementation-plan.md)。本文明确当前起点和后续提交边界，不替换原有契约。

## Global Constraints

- 开发目录：`C:/Users/zhuohongze/Desktop/oj-test-platform`。保留原始 `cpp-oj-vibecoding` 源码。
- 本轮只整理方案，不修改业务代码、运行修复或提交推送。
- Python 3.12 为主验收版本，3.14 为兼容性目标。
- 单平台执行进程、单个运行任务、最多 20 个等待任务；并发 worker 范围 1–16。
- 密码、Token、Cookie 不入库、不进报告、不提交；提交请求不透明重试。
- Mock 通过不等于真实判题通过；工作流文件存在不等于 GitHub Actions 已运行。
- 已有未提交改动必须保留、逐项审查，不能用清理或重置命令消除。

## 当前起点（2026-10-02 本地核对）

本地 HEAD：`35bad0ed14f6a37947315e7085851627427d00c1`。
分支：`step/06-bounded-concurrency`。本轮未重新查询远端，也未重跑历史测试。

| 阶段 | 已有记录 | 本轮后的处理 |
|---|---|---|
| S00–S03 | 基线、Mock、严格断言、配置/入口已验收 | 不重复建设；保留回归覆盖 |
| S04 | 两道 YAML 题目、策略、种子和源码快照已验收 | S10 再证明真实算法判题 |
| S05 | SQLite、历史、恢复与运行锁已在 Windows/Mock 验收 | Linux 行为在容器/CI 验收 |
| S06a | 有界并发与独立会话已提交；进度记录为 226 条测试通过 | 不把该记录当成本轮重新测试结果 |
| S06b | 6 个已跟踪文件修改和新增取消测试未提交 | 第一项实施工作：完成取消一致性修复及回归 |
| S07–S12 | 尚未验收 | 按下面顺序实施 |

## 任务 1：完成 S06b 取消与最终报告一致性

**文件：** `task_center/service.py`、`core_engine/executor/{base,sequential,concurrent}_executor.py`、`core_engine/report_engine/report_generator.py`、`tests/integration/test_cancellation.py`。

**接口：** 沿用 `TaskService.cancel(task_id)`、`close(timeout=30)`、`_write_reports(task_id)` 和取消 Event；不另建一套取消机制。

**问题：** 当前 `_run` 在 `_condition` 外生成报告，再进入锁更新终态。取消可以发生在两者之间，造成数据库为 CANCELLED，而已生成报告仍表示未取消。已有确定性屏障测试覆盖该时序。

- [ ] 阅读并保留当前全部差异；复现下面的报告/取消测试。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/integration/test_cancellation.py::test_report_publication_and_terminal_state_are_serialized_with_cancel -q
```

- [ ] 将报告快照、报告发布及终态转换置于同一 `_condition` 临界区。取消先取得锁则进入取消终态；报告发布先取得锁并完成后，取消返回终态冲突。
- [ ] 同时修复 `close` 的总截止时间：获取条件锁和等待执行线程共用同一 deadline；无法在期限内关闭时抛出超时，并保留执行锁。不能为了报告一致性让 `close(timeout=0)` 无限等待。
- [ ] 验证取消后无新增提交、在途结果保存、未提交用例 attempt_count 为 0、取消标记进入两种报告、CLI 中断退出码 130。记录测试中模拟 Python SIGINT 与真实操作系统控制台信号的区别。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/integration/test_cancellation.py tests/integration/test_concurrency.py -q
.\.venv\Scripts\python.exe -X utf8 -m pytest -m "not e2e" -q --junitxml=artifacts/s06b.xml
```

- [ ] 审查通过后单独提交：`fix: make cancellation stop further submissions`。

**验收：** 最终统计守恒；已接受的取消不被 COMPLETED 覆盖；报告与任务状态一致；超时关闭不提前释放运行锁。取消不承诺杀死远端程序。

## 任务 2：S07 失败报告可复现

**文件：** `core_engine/report_engine/report_generator.py`、`task_center/service.py`、`storage/repository.py`、`backend/routers/report_router.py`；新增 `tests/unit/test_reports.py`、`tests/integration/test_report_endpoints.py`。

**接口：** 按原计划引入 `ReportGenerator(root).generate(task_snapshot)`；同步迁移所有调用方，返回报告 ID、格式、相对路径及哈希。快照来自数据库，不依赖最近一次 Adapter 结果。

- [ ] 第一提交：统一报告快照，包含实际源码、题号、配置、seed、预期/实际/原因、平台及被测版本、源码和 profile 哈希；JSON/HTML 统计一致。
- [ ] 第二提交：动态 HTML 转义、秘密脱敏、UUID 路径、临时文件原子替换、报告元数据完整发布及写盘失败处理。
- [ ] 增加恶意 HTML 输入、同秒多报告、缺失/篡改文件、路径越界、部分写入失败测试。失败时不能出现成功任务指向缺失报告。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/unit/test_reports.py tests/integration/test_report_endpoints.py -q
```

**验收：** 仅凭保存的报告即可找到真实提交输入及失败原因；源码安全显示；不泄露凭据；重启后可下载同一报告。

## 任务 3：S08 Web 完整操作流程

**文件：** `frontend/index.html`、`backend/routers/task_router.py`、`backend/routers/config_router.py`；新增 `tests/integration/test_web_api_contract.py`、`docs/manual-web-checks.md`。

- [ ] 第一提交：页面接入 v1 API，显示 profile、题号、策略、数量、seed、执行模式及 worker 数；顺序模式固定 1 worker。
- [ ] 第二提交：历史任务详情、输入/结果、取消过程、报告下载与错误信息；动态文本使用 textContent；活动任务不能删除。
- [ ] 执行接口契约测试，再真实操作浏览器：创建顺序任务、查看进度和失败详情、下载双格式报告、创建并发任务并取消、刷新、重启后查看历史。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/integration/test_web_api_contract.py -q
```

**验收：** 保存实际任务 ID、截图与操作结果；接口测试通过不能替代页面操作验收。

## 任务 4：S09 Docker 可安装交付

**文件：** `Dockerfile`、`.dockerignore`、`compose.yaml`、`.env.example`、`scripts/smoke_compose.py`、`docs/docker.md`。

- [ ] 构建 platform/mock-oj/smoke；平台非 root、单 worker；SQLite 和报告放持久卷。
- [ ] smoke 的 create 阶段创建非空任务、下载报告并保存 task_id/哈希；verify 阶段核对同一任务及报告。
- [ ] 核验 Linux 引擎后构建并启动，分别验证 restart 和普通 down/up 后历史仍在。不得用删除卷的操作证明持久化。

```powershell
docker compose --profile demo config
docker compose --profile demo up -d --build
docker compose --profile demo run --rm smoke --phase create
docker compose restart platform
docker compose --profile demo run --rm smoke --phase verify
```

**验收：** 容器真实运行、报告及数据库持久化、Linux 运行锁生效；引擎不可用时记录 BLOCKED，不声称 Docker 已完成。

## 任务 5：S10 真实 C++ OJ 联调

**文件：** `infra/cpp-oj.Dockerfile`、`compose.e2e.yaml`、`scripts/prepare_sut.ps1`、`scripts/seed_e2e.py`、`scripts/cleanup_e2e.py`、`tests/e2e/test_real_oj.py`、`docs/e2e.md`。

- [ ] 第一提交：独立检出并核验设计文档指定 C++ SHA，建立专用 MySQL 和两道题；fixture 清单记录 run_id、精确 ID 与内容哈希。
- [ ] 第二提交：两道题 × AC/WA/CE/TLE/RE × 顺序/并发入口；另测多用例批量并发、认证失败、缺失题目和取消。
- [ ] 所有 verdict 必须来自真实编译执行；保留响应和环境版本。发现 C++ 缺陷单独归因，不在 Adapter 中伪造结果。
- [ ] 按清单精确清理本次数据并读回，不清空共享表。

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/e2e --run-e2e -q --junitxml=artifacts/e2e.xml
```

**验收：** 原计划定义的 E2E 配置和 fixture 前置步骤完成后再运行；真实结果支持简历五类判题描述。

## 任务 6：S11 CI 回归与制品

**文件：** `.github/workflows/regression.yml`、`scripts/check_evidence.py`、`tests/unit/test_evidence_gate.py`、`docs/ci.md`。

- [ ] 第一提交：非空测试/报告证据门禁，失败、零用例、缺制品都返回非零；本地验证后接工作流。
- [ ] 第二提交：Python 回归矩阵、Docker smoke、JUnit/HTML/JSON 归档；S10 完成后接 E2E job。使用官方文档核验 Actions 并固定提交版本。
- [ ] 获取并核验用户的 GitHub 仓库 URL 后使用第二远端；Gitee 保持 origin。
- [ ] 同一提交运行真实绿色流水线并下载制品；独立验证分支证明失败测试能让流水线变红，同时保存制品。

**验收：** run URL、平台 SHA、制品下载和解析证据齐全。只有 Gitee 推送或 workflow 文件不能证明 Actions 通过。

## 任务 7：S12 最终交付

**文件：** `README.md`、`OJ测试开发工具.md`、`docs/acceptance.md`、`docs/troubleshooting.md`、`docs/evidence/index.json`。

- [ ] 将每一条简历描述映射到代码、测试节点、环境、验证 SHA 及制品。
- [ ] 干净检出安装，运行回归、Docker smoke 和具备环境的真实联调；记录 PASS/FAIL/BLOCKED/NOT_RUN。
- [ ] 核对 Gitee 最终提交；全部必要验收通过后才发布交付标签。

**验收：** 可由另一份干净检出复现；文档明确平台 SQLite 与被测 OJ MySQL 的不同职责。

## 每个提交的固定操作

1. 仅处理当前任务边界，先有失败复现，再实现并验证。
2. 聚焦测试通过后运行非 E2E 回归；保存环境、命令、退出码和证据，不硬编码预期通过数量。
3. 显式暂存本阶段文件，检查差异及秘密；更新进度和证据摘要。
4. 提交并推送阶段分支；审核后快进 main 并推送，分别读回远端 SHA。
5. 汇报“改了什么、如何验证、提交 SHA、远端地址、剩余缺口”。失败就停在该阶段修复，不连带提交后面的功能。

当前工作区有 S06b 未提交改动，因此先完成任务 1；不要直接从脏工作区切换 main 或创建后续阶段分支。后续阶段具体提交主题和文件级步骤沿用完整实施计划。

## 自检

- 简历各项能力对应 S02/S04/S05/S06/S07/S08/S09/S10/S11，交付证据归 S12。
- 当前已有实现不重做；S06b 的报告一致性及关闭超时明确纳入第一步。
- 每个阶段都有文件、验证动作和完成标准；历史测试记录与本轮操作分开。
- Docker 和 GitHub 的环境前提不阻塞前段本地修改；缺前提的验收保持未通过状态。
