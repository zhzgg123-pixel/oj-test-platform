> 规划快照（2026-10-02）。用户现已授权执行及分步推送；文中的“本轮不修改”描述的是规划阶段。当前进度以 progress.md 为准。

# OJ 自动化测试平台改造：设计与验收约定

日期：2026-10-02。本文是待实施设计，不是已完成能力清单。依据为用户提供的简历、桌面源码和同目录《OJ自动化测试平台-简历对照与补齐建议.md》。本轮不改项目代码、不提交、不推送。

## 1. 目标和版本边界

目标：让简历中每项 OJ 平台描述都有对应代码、自动化测试和可查看的运行证据。保留现有 FastAPI、适配器、生成器、执行器、静态前端的模块划分，逐步修复和接通。

| 对象 | 已核实状态／本方案决定 |
|---|---|
| Python 来源 | `C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform`，当前不是 Git 仓库 |
| C++ 来源 | 同级 `cpp-oj`，本地 HEAD `84ded72d705cd9e950ad5d4d644e1cefdb4775d5`，本轮检查工作区干净 |
| C++ 远端 | `https://gitee.com/chasing-dreams-zhuo/cpp-oj`；本轮查询 master 为 `cede96af7ea62f07bc1fbc0c466658b771b57777`，与本地不同 |
| 新平台仓库 | `https://gitee.com/chasing-dreams-zhuo/oj-test-platform`，私有、空仓库，当前账户具备 push/admin 权限 |
| 后续开发目录 | 计划新建 `C:/Users/zhuohongze/Desktop/oj-test-platform`，直接以 Python 平台为仓库根目录；默认分支选 `main` |
| 被测系统版本 | 真实联调采用独立检出的 C++ 固定提交 `cede96af7ea62f07bc1fbc0c466658b771b57777`；执行前核验其存在及内容，不直接更新原目录 |
| 运行环境 | 本机 Python 为 3.14.2；方案以 Python 3.12 为容器和主验收版本，3.14 为兼容性测试版本。3.12 虚拟环境需要在实施时准备 |
| Docker | 命令可用，当前 Docker Desktop Linux 引擎未连接；容器与真实 OJ 联调尚不可认定通过 |
| GitHub Actions | 用户确认有 GitHub 仓库，但本对话未得到 URL；这只影响后段的真实 Actions 验收，不阻塞前段本地开发 |

不得把其他路径的历史版本、旧 HTML 报告或 C++ 自身的测试算作本平台已完成的能力。首次导入记录原始文件 SHA256 清单和筛选规则，建立可追溯基线。

## 2. 简历要求对应的交付

| 简历要求 | 最小充分交付 | 验收阶段 |
|---|---|---|
| YAML 题目规则、三类策略 | 两道算法逻辑不同的题目 YAML、模板、schema、确定性 seed；新增题目不改执行器 | S04 |
| Adapter 登录／提交／查询 | 明确响应契约、业务拒绝、超时和传输错误；每个执行 worker 独立会话 | S02、S06 |
| Web 和 CLI | 同一配置模型、任务服务和结果模型，非法请求一致拒绝 | S03、S05、S08 |
| 顺序和线程池并发 | 入口能选模式、worker 上限、受控调度、真实重叠证据 | S06、S10 |
| SQLite 历史追溯 | 配置快照、实际提交输入、逐条结果、报告关联；新进程可查询 | S05 |
| AC/WA/CE/TLE/RE 校验 | 五种状态严格匹配；未知状态与协议异常不被当作通过；真实 OJ 逐项验证 | S02、S10 |
| HTML／JSON 失败报告 | 提交源码、预期与实际、错误详情、seed、题目与环境版本可复现 | S07 |
| pytest + Mock Server | 真 HTTP Mock 服务、平台路由测试、故障注入、隔离数据及清理 | S01 起贯穿 |
| Docker | 可构建镜像、健康检查、持久卷、容器重启后可查历史 | S09 |
| GitHub Actions 回归和归档 | 同一代码提交真实运行、失败门禁、可下载的 JUnit／HTML／JSON 制品 | S11 |

## 3. 必须先修复的行为

1. `expected_status=ERROR` 不能再表示“什么结果都算通过”。改为具体错误预期，例如 HTTP 401，或 HTTP 200 加 `PROBLEM_NOT_FOUND`。
2. 空策略、未知策略、零用例、登录失败不能得到成功退出码。
3. `LocalOJAdapter` 必须识别 HTTP 200 下的 `success:false`；缺少判题字段应立即成为协议错误，不能等待不存在的结果。
4. 不允许共享可变 Adapter／Session 或 `_last_judge_result` 导致任务结果串扰。
5. 取消必须作用于调度流程，不能只改页面状态后又被完成状态覆盖。
6. HTML 和 JSON 使用同一完整结果快照；不保存密码、令牌、Cookie，不直接拼接未经转义的错误文本。

## 4. 架构和模块责任

```text
Web / CLI
    ↓ TaskConfig 校验 + 临时 ExecutionCredentials
TaskService → ProfileLoader → CaseBuilder → 实际 TestCase 快照
    ↓ SQLite 先保存任务和输入
顺序执行器 / 有界线程池
    ↓ worker 独立 Adapter → RequestClient → C++ OJ / Mock OJ
    ↓ JudgeOracle.evaluate → CaseResult → SQLite 逐条保存
ReportGenerator ← SQLite 一致快照 → HTML / JSON → Web 历史详情
```

| 路径（相对新平台仓库根目录） | 职责 |
|---|---|
| `core_engine/contracts.py`（新增） | 不含网络／数据库调用的预期、观察结果、测试结果契约 |
| `core_engine/assertion/judge_oracle.py` | 唯一的断言入口；执行器不再复制判定分支 |
| `plugins/base_adapter.py`、`plugins/local_oj/adapter.py` | Adapter 契约与当前 C++ 协议映射 |
| `plugins/plugin_manager.py` | 注册和创建 Adapter 工厂；取消实例级全局缓存 |
| `config_center/models.py`、`config_center/profile_loader.py`（新增） | 统一任务配置校验；安全加载题目 YAML 和模板 |
| `profiles/*.yaml`、`profiles/templates/*`（新增） | 题目规则和程序模板；不包含账号密码 |
| `core_engine/case_engine/*` | 按 profile 与 seed 生成具体 TestCase |
| `storage/database.py`、`storage/repository.py`、`storage/migrations/001_initial.sql`（新增） | SQLite 初始化、版本、短事务和查询 |
| `task_center/service.py`、`task_center/runtime.py`（新增） | Web／CLI 共用编排；运行锁、队列、凭据内存、取消事件 |
| `task_center/task_manager.py` | 保留原路由可用的薄兼容层，逐步委托 TaskService |
| `core_engine/executor/*` | 选择执行模式、提交、查询、取消与逐条结果回调 |
| `core_engine/report_engine/report_generator.py` | 从完整结果生成一致的两种报告 |
| `backend/app.py`、`backend/routers/*`、`main.py` | 生命周期、协议转换、退出码；不另写一套任务逻辑 |
| `frontend/index.html` | 保留现有静态页面，补参数、任务详情和历史 |
| `tests/mock_oj/server.py`、`tests/unit/*`、`tests/integration/*`、`tests/e2e/*`（新增） | 平台测试、可控 HTTP 服务、显式启用的真实联调 |

不引入 Redis、Celery、微服务或新的前端框架。这些不是本次简历要求；先完成单机、单平台进程、线程池执行的完整链路。

## 5. 数据契约

以下为新契约，实施时统一定义，旧返回字段通过兼容层迁移。

### 5.1 配置与实际输入

`TaskConfig`：`adapter_name, base_url, profile_id, problem_id, strategies, case_count, seed, mode, max_workers, request_timeout, poll_interval, poll_timeout`。

- `strategies` 非空且只允许 `random/boundary/rule`；`case_count` 为最终生成总数，范围 1–1000，且不少于所选策略数。按策略轮转分配，使每个选中策略至少产生一条。
- `mode` 为 `sequential/concurrent`；顺序模式强制 `max_workers=1`，并发范围 1–16。
- `seed` 为显式整数，默认 42；所有随机源来自任务级 `random.Random(seed)`，不得使用隐式全局随机数。
- 超时和轮询间隔为正数，`poll_timeout >= poll_interval`；URL 限制 http/https；配置缺失／未知值直接失败。
- `ExecutionCredentials(username, password)` 仅驻留内存。密码采用秘密字段类型，日志及异常序列化不输出原值。数据库和报告只保存允许的非秘密配置字段。
- `TestCase` 增加 `strategy, source_code, source_sha256, expectation, auth_mode, request_overrides, profile_sha256, seed`；兼容旧 `code` 入口后统一归一化。

**“测试输入”的准确范围：**当前 Adapter 发送题号、程序源码和 lang 字段，C++ handler 实际只读取源码并固定按 C++ 编译；题目 stdin／期望 stdout 存在 OJ 端。平台首先保存实际提交请求及题目 fixture 快照。YAML 的随机策略实现“按 seed 采样题目模板和参数”，不能宣传为对 OJ 注入任意随机 stdin。若以后需要数值输入生成，必须另做 OJ 测试数据管理或独立运行协议，并增加真实数据变更证据。

### 5.2 判定和错误

在 `core_engine/contracts.py` 定义：

```python
Expectation(kind="verdict", verdict="AC")
Expectation(kind="http_error", http_status=401)
Expectation(kind="business_error", http_status=200, error_code="PROBLEM_NOT_FOUND")

Observation(kind="verdict", verdict="WA", http_status=200, evidence={})
Observation(kind="business_error", http_status=200, error_code="PROBLEM_NOT_FOUND", evidence={})
Observation(kind="transport_error", error_code="READ_TIMEOUT", evidence={})
```

`kind` 使用枚举／受限字面量；通过校验禁止没有所需字段的组合。Observation 另支持 `http_error/protocol_error`。当前 OJ 未返回稳定业务代码时，LocalOJAdapter 将已经核实的精确错误消息映射为内部代码；未知消息保留脱敏证据并报协议错误，不做宽松子串猜测。

`JudgeOracle.evaluate(expected: Expectation, observed: Observation) -> AssertionResult`，返回 `status=PASSED/FAILED/ERROR` 与 `reason`。

| 实际观察 | 预期匹配 | 结果 |
|---|---|---|
| AC/WA/CE/TLE/RE 判题结果 | 判题状态相同 | PASSED，否则 FAILED |
| 明确 HTTP 拒绝 | kind 和 HTTP 码匹配 | PASSED，否则 FAILED |
| 明确业务拒绝 | kind、HTTP 码、业务码全部匹配 | PASSED，否则 FAILED |
| 超时、网络断开、未知／缺字段响应、平台异常 | 不能证明业务预期 | ERROR |
| 正常 AC | 预期为任何拒绝 | FAILED |

默认不根据硬编码的时间、内存或 `passed<total` 改写 OJ 判题状态。资源指标只作为证据；做额外一致性检查时必须使用真实题目限制和真实返回字段。

Adapter 方法：`login(credentials) -> AuthResult`、`submit_case(case) -> SubmissionReceipt`、`get_result(submission_id) -> Observation | None`、`close() -> None`。Receipt 包含本地／远端 submission_id 与可选的 immediate_observation。同步 OJ 可直接返回观察值；异步 OJ 才轮询。结果不能存入“最近一次结果”的共享槽位。

RequestClient：GET 仅对连接失败／超时／502/503/504 进行最多两次额外重试；POST 提交默认不透明重试，避免已收到请求但响应丢失时重复执行。明确 401 默认按契约报告；不得将负向认证用例自动登录后重发。

### 5.3 任务状态、取消和计数

```text
PENDING → RUNNING → COMPLETED
    └→ CANCELLED       ├→ FAILED
                      └→ CANCEL_REQUESTED → CANCELLED
重启恢复：遗留 PENDING/RUNNING/CANCEL_REQUESTED → INTERRUPTED
```

- `COMPLETED` 表示所有用例执行完，不代表用例全部通过。配置准备失败／登录失败／持久化或报告失败为任务 `FAILED`，保存阶段和原因。
- 用例状态为 `PENDING/RUNNING/PASSED/FAILED/ERROR/CANCELLED`。执行中总数始终满足六类相加等于 total；终态无 PENDING/RUNNING。
- `success` 仅在任务 COMPLETED、total>0、passed==total 且必需报告生成成功时为真。
- 取消设置 Event；调度器停止取新用例；未提交的标 CANCELLED；已提交的只等待到已配置截止时间，保留实际结果。最后任务仍为 CANCELLED。
- 不承诺终止远端已经提交的 C++ 程序；报告记录 `remote_execution_may_continue`。真实强杀需要 OJ 提供取消协议。
- 一个平台进程最多一个 RUNNING 任务，内存等待队列上限 20；每个任务最多 16 个 worker。超过队列上限返回 429。这个界限用于可预测演示，不作为生产容量结论。
- 同一数据库只允许一个执行进程持有操作系统文件锁。Web 已运行时 CLI 直接运行同库必须明确失败，可使用独立 `--db runtime/ci.db`。只读历史查询允许并行；不能由第二个实例将正在运行的任务标成 INTERRUPTED。

### 5.4 SQLite 与恢复

四张业务表：

| 表 | 关键字段 |
|---|---|
| `tasks` | id(UUID), state, config_json, profile_json, profile_sha256, platform_sha, sut_sha, created_at, started_at, finished_at, error_json |
| `task_cases` | id(UUID), task_id(FK), ordinal, strategy, input_json, expectation_json, source_sha256, state；唯一(task_id, ordinal) |
| `case_results` | case_id(PK/FK), assertion_status, actual_json, reason, duration_ms, attempt_count, started_at, finished_at |
| `reports` | id(UUID), task_id(FK), format, relative_path, sha256, created_at |

使用 `PRAGMA user_version` 管理迁移版本；启用外键、WAL、busy_timeout。按操作创建连接，不跨线程共享默认 SQLite connection；不在数据库事务内发 HTTP 请求。生成完成后先原子保存任务、profile 快照与全部实际输入，再开始任何提交。每条结果以独立短事务更新。

运行状态更新采用条件更新，例如 `WHERE state='RUNNING'`，避免完成覆盖取消。重启取得独占运行锁后，将遗留活动任务改 INTERRUPTED，保留完成结果，其余用例归为 ERROR、原因 PROCESS_INTERRUPTED。重跑创建新 task_id 并要求重新提供凭据，不复用已经部分执行的任务。

### 5.5 API、CLI、报告

平台新增统一 v1 API；旧路由继续委托同一个服务，过渡期不删旧入口：

- `POST /api/v1/tasks`：校验、保存并排队，返回 202 和 task_id。
- `GET /api/v1/tasks?limit=20&offset=0`：按创建时间倒序，limit 最大 100。
- `GET /api/v1/tasks/{id}`、`GET /api/v1/tasks/{id}/cases`：配置快照、统计、具体输入和结果。
- `POST /api/v1/tasks/{id}/cancel`：活动任务接受取消；终态 409；不存在 404。
- `GET /api/v1/tasks/{id}/reports/{format}`：仅从 reports 表定位报告；format 限 html/json，拒绝任意路径。
- `DELETE /api/v1/tasks/{id}`：活动任务 409；终态才允许删除，文件路径须位于报告根目录。
- `GET /api/v1/profiles`：返回可用配置摘要；创建任务时仍重新校验。

CLI 保留 `python main.py --ci`，增加 `--config --profile --problem-id --mode --max-workers --seed --case-count --db --report-dir`。密码通过环境变量 `OJ_PASSWORD` 或交互输入，不放命令参数。优先级：CLI 显式项 > 环境变量 > 指定配置文件 > 默认值。退出码：0 全部通过，1 用例失败／运行异常／中断，2 参数错误／运行锁冲突，130 用户 Ctrl+C。

报告以 UUID 目录及原子写入避免重名覆盖；从数据库读取同一快照生成两种格式。每条失败包含具体提交源码、题目与 seed、预期／实际、HTTP／业务错误、耗时、Adapter、平台版本和被测版本。允许列出 fixture 的 stdin／stdout，但明确它们是已部署题目数据快照。统一字段 `error`，修复前端的 `errors` 拼写不一致。HTML 转义所有动态文本；前端使用 textContent 等安全赋值。原始响应按字段白名单保存，并对异常文本二次清理已知秘密。

## 6. 验证层次

| 层次 | 能证明什么 | 不能替代什么 |
|---|---|---|
| pytest unit | 配置、生成、Oracle、统计、存储逻辑 | 真实 OJ 协议和编译运行 |
| pytest integration + 真 HTTP Mock | 登录 Cookie、提交／轮询、超时、并发隔离、平台 API | 五类真实编译／判题结果 |
| Docker platform + Mock | 镜像构建、网络、健康、卷持久化 | C++ OJ 和 MySQL 真实联调 |
| pytest e2e + 固定 C++ OJ | 两道题与五种判题状态、真实认证、顺序／并发 | 容量或生产安全隔离结论 |
| GitHub Actions | 指定提交自动回归、失败门禁、制品 | 未实际运行的 E2E 能力 |

证据采用 PASS / FAIL / BLOCKED / NOT_RUN。当前“已审计到的缺陷”不自动变为“已修复”。每步证据记录 command、退出码、代码 SHA、环境、测试数量、报告位置；密码等敏感字段不得进入证据。

## 7. 使用的官方文档

通过 Context7 核对，实施时遇到具体版本 API 仍需重新确认：

- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/) 与 [TestClient 生命周期测试](https://fastapi.tiangolo.com/advanced/testing-events/)：在 lifespan 初始化／关闭资源，用上下文管理器执行生命周期测试。
- [pytest tmp_path](https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/tmp_path.rst)、[fixtures](https://github.com/pytest-dev/pytest/blob/main/doc/en/how-to/fixtures.rst)：每个测试独立数据库／报告路径，用 yield 清理服务。
- [Docker Compose down](https://github.com/docker/compose/blob/main/docs/reference/compose_down.md)：普通 down 与删除卷是不同操作；重启验收不使用 `down -v`。
- [GitHub Actions 入门](https://docs.github.com/en/actions/get-started/quickstart)、[归档制品](https://docs.github.com/en/actions/tutorials/store-and-share-data)：工作流放在 `.github/workflows/`，实际运行与下载制品另行验收。
