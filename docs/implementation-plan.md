> 规划快照（2026-10-02）。用户现已授权执行及分步推送；文中的“本轮不修改”描述的是规划阶段。当前进度以 progress.md 为准。

# OJ 自动化测试平台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `executing-plans` 按任务逐步实施；未经用户选择，不自行启用多代理。下列复选框表示尚未执行的工作。

**Goal:** 逐步使桌面 Python OJ 平台满足简历描述，并以独立提交、真实测试和远端 SHA 建立证据。

**Architecture:** 保留现有模块，先统一判定和配置，再接入 YAML、SQLite、线程池与报告。Web 和 CLI 委托同一个 TaskService；Mock 与真实 C++ OJ 分层验证。

**Tech Stack:** Python 3.12 主验收／3.14 兼容性测试、FastAPI、Pydantic、SQLite、pytest、现有 HTTP 客户端、Docker Compose、GitHub Actions；Gitee 保存代码。

**Spec:** [OJ平台改造-设计与验收约定.md](design-contract.md)，实施前先读；缺陷依据见 [原始审计](initial-audit.md)。

## Global Constraints

- 本文为待执行计划；本轮不改项目代码、不提交、不推送。
- 后续工作目录为 `C:/Users/zhuohongze/Desktop/oj-test-platform`；原始 `cpp-oj-vibecoding` 目录保留。
- Gitee origin 为 `https://gitee.com/chasing-dreams-zhuo/oj-test-platform.git`；默认分支选 `main`。
- Python 3.12 为容器和主验收版本，3.14 为兼容性测试版本。
- 同一数据库只允许一个执行进程持有操作系统文件锁；Web 默认一个 Uvicorn worker。
- 一个平台进程最多一个 RUNNING 任务，内存等待队列上限 20；每个任务最多 16 个 worker。
- 密码、令牌、Cookie 不入库、不进报告、不提交 Git；请求 POST 不透明自动重试。
- 真实联调独立检出 C++ `cede96af7ea62f07bc1fbc0c466658b771b57777`，不直接更新原目录。
- 每步完成“复现／红测 → 实现 → 绿测 → 审查差异 → 提交 → 推送 → 远端读回”。不以文件存在代替运行成功。

## 0. 实施总览

| 阶段 | 可检查的产物 | 依赖 | 建议提交主题 |
|---|---|---|---|
| S00 | 新仓库基线、来源清单、开发环境 | 无 | `chore: import sanitized platform baseline` |
| S01 | pytest 和可控 HTTP Mock | S00 | `test: add isolated mock OJ harness` |
| S02 | 正确断言、Adapter 契约、重试边界 | S01 | `fix: enforce explicit OJ result contracts` |
| S03 | 配置校验、入口一致、退出码 | S02 | `fix: reject invalid and empty task runs` |
| S04 | 两道题 YAML、三类策略、seed | S03 | `feat: generate cases from problem profiles` |
| S05 | SQLite、历史查询、进程恢复 | S04 | `feat: persist task inputs and results` |
| S06 | 公开并发入口、会话隔离、取消 | S05 | `feat: add bounded concurrent task execution` |
| S07 | 可复现的 HTML／JSON 失败报告 | S05、S06 | `feat: generate traceable safe test reports` |
| S08 | Web 操作和历史详情完整闭环 | S07 | `feat: expose task controls and history in web UI` |
| S09 | Docker 构建、Mock 演示、卷持久化 | S08 | `build: containerize platform and mock demo` |
| S10 | 固定版本真实 C++ OJ 联调 | S09 | `test: verify platform against pinned cpp OJ` |
| S11 | GitHub Actions 真实回归与归档 | S09；E2E 作业依赖 S10 | `ci: run regression and archive test evidence` |
| S12 | 使用文档、验收表、版本交付 | 全部 | `docs: publish verified platform acceptance evidence` |

S05 和 S06 较大，下面分别设置可独立检查的子提交。不要把 13 个阶段一次性实现后才提交。

## S00：建立可回退的基线

**文件**：导入现有 `backend/ config_center/ core_engine/ plugins/ task_center/ frontend/ main.py requirements.txt`；新增 `.gitignore`、`README.md`、`docs/baseline.md`、`docs/source-manifest.json`、`docs/implementation-plan.md`、`docs/design-contract.md`。

**输入／输出**：输入桌面 Python 原始源码；输出 main 上可校验的首次提交及来源 SHA256 清单。后续路径均相对此新仓库。

- [ ] 重新核实目标目录不存在或为空、远端仍为空、源目录没有新增指令文件；不覆盖已有目录。记录原始平台清单与 C++ 本地／远端 SHA。
- [ ] 仅导入白名单业务源码。排除 `.git/ .venv/ __pycache__/ reports/ runtime/ .env* tp_b64_* serve_tp.py` 和本地密钥。检查 `config.yaml/config.prod.yaml` 及文档中的真实凭据，将提交副本改成非秘密示例；不改原始文件。
- [ ] `.gitignore` 至少包含下列项；配置中的假账号也不得被误写成可用的默认管理员密码。

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.coverage*
htmlcov/
.env
.env.*
!.env.example
runtime/
reports/
artifacts/
*.db
*.db-*
*.sqlite*
*.log
.cache/
tp_b64_*
```

- [ ] 在新目录建立 Python 3.12 虚拟环境；若尚未安装，先准备该版本再执行。保留当前 Python 3.14 系统环境。先安装现有 requirements，记录安装结果；版本冲突单独处理并说明，不把全局环境 freeze 到项目。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m compileall -q backend config_center core_engine plugins task_center main.py
```

- [ ] 比较导入文件与来源哈希，逐项解释脱敏和排除差异；检查 git 暂存内容不含旧报告或敏感数据。此时不声称回归通过，baseline 文档记录 tests 为空和已知缺陷。
- [ ] 在目标目录执行以下命令；先确认 `git diff --cached` 内容，再 commit/push。推送失败保留本地提交，不换目标、不 force。

```powershell
git init -b main
git remote add origin https://gitee.com/chasing-dreams-zhuo/oj-test-platform.git
git add .gitignore README.md docs backend config_center core_engine plugins task_center frontend main.py requirements.txt
git diff --cached --stat
git diff --cached --check
git commit -m "chore: import sanitized platform baseline"
git push -u origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

**验收**：本地与远端 main SHA 相同、来源可追溯、原目录未改变、秘密未进入提交。此次只是基线验收，不是业务验收。

## S01：让平台拥有自己的测试底座

**创建**：`requirements-dev.in`、`requirements-dev.lock`、`pytest.ini`、`tests/conftest.py`、`tests/helpers.py`、`tests/mock_oj/__init__.py`、`tests/mock_oj/server.py`、`tests/integration/test_mock_harness.py`。

**接口**：`MockOJServer(scenario: str).start(host="127.0.0.1", port=0)`；提供 `base_url, requests, max_active_submissions, block_submissions, release_submissions, close()`。请求日志只记录脱敏字段。pytest fixture `mock_oj` 自动 start/yield/close。`tests.helpers.wait_until(predicate, timeout=5)` 使用 monotonic 截止时间，超时抛 AssertionError。

Mock 实现真实 HTTP 路由 `/api/login`、`/api/submit/{id}`，使用与本地 OJ 核实一致的响应。预设 `all-verdicts/login-rejected/problem-not-found/malformed/slow/disconnect` 场景；按提交源码标记选择判题结果。需要支持 Cookie 校验、阻塞释放事件、活动请求计数；不要通过改平台代码来决定 Mock 结果。

- [ ] 先加入以下红测，Mock 模块尚不存在时应收集失败；记录失败原因。

```python
import requests

def test_unknown_problem_uses_real_http(mock_oj):
    session = requests.Session()
    login = session.post(mock_oj.base_url + "/api/login",
                         json={"username": "tester", "password": "test-only"}, timeout=2)
    assert login.status_code == 200
    response = session.post(mock_oj.base_url + "/api/submit/999999",
                            data={"code": "int main(){}", "lang": "cpp"}, timeout=2)
    assert response.status_code == 200
    assert response.json()["success"] is False
    session.close()
```

- [ ] 命令 `python -m pytest tests/integration/test_mock_harness.py -q` 先确认红测，再实现 Mock。当前 Adapter 提交表单 `code/lang`，C++ handler 实际读取 code、固定按 C++ 编译，不校验 lang；Mock 必须保留这个事实，不能自行增加语言拒绝行为。
- [ ] 注册 `unit/integration/e2e` markers，默认不运行 e2e；通过显式 `--run-e2e` 开关启用。E2E 被指定运行却缺少目标配置时直接失败，不能全 skip 后绿色退出。
- [ ] fixture 为每个测试创建 tmp_path DB／报告目录，HTTP 端口由系统分配，finally 释放阻塞事件并关闭线程；加入连续启动／关闭两次的用例。
- [ ] 在干净 venv 中安装 pytest 与所需测试依赖，再生成并验证精确版本锁文件。执行 `python -m pytest tests/integration/test_mock_harness.py -q --junitxml=artifacts/s01.xml`。
- [ ] 审查 fixture 没有真实数据库／OJ 地址；绿测后提交 `test: add isolated mock OJ harness`，按末尾流程推送。

**验收**：不依赖 C++／MySQL／Docker 即可运行；没有监听端口或线程遗留。测试数和 JUnit 真实可查。

## S02：先修复误判及协议解析

**新增／修改**：新增 `core_engine/contracts.py`；修改 `plugins/base_adapter.py`、`plugins/local_oj/adapter.py`、`core_engine/api_client/request_client.py`、`core_engine/assertion/judge_oracle.py`、`core_engine/executor/sequential_executor.py`；测试 `tests/unit/test_judge_oracle.py`、`tests/integration/test_local_adapter.py`、`tests/integration/test_retry_policy.py`。

**接口**：产生设计文档的 `Expectation/Observation/AssertionResult/SubmissionReceipt/AuthResult`。`JudgeOracle.evaluate(expected, observed)` 是唯一断言入口；LocalOJAdapter 同步响应通过 `immediate_observation` 返回，轮询仅用于异步 receipt。

- [ ] 写下面的参数化红测及五类状态相等／不等矩阵；原来的泛化 ERROR 分支不能兼容为“任意错误通过”。

```python
import pytest
from core_engine.contracts import Expectation, Observation
from core_engine.assertion.judge_oracle import JudgeOracle

@pytest.mark.parametrize("observed,status", [
    (Observation(kind="verdict", verdict="AC", http_status=200), "FAILED"),
    (Observation(kind="http_error", http_status=401), "FAILED"),
    (Observation(kind="transport_error", error_code="READ_TIMEOUT"), "ERROR"),
    (Observation(kind="business_error", http_status=200,
                 error_code="PROBLEM_NOT_FOUND"), "PASSED"),
])
def test_business_rejection_is_specific(observed, status):
    expected = Expectation(kind="business_error", http_status=200,
                           error_code="PROBLEM_NOT_FOUND")
    assert JudgeOracle().evaluate(expected, observed).status == status
```

- [ ] `python -m pytest tests/unit/test_judge_oracle.py -q` 确认失败；实现 typed contracts 和严格 Oracle，删除 WA 仅靠 passed 数判断、RE 依赖缺失字段、固定 TLE/MLE 阈值推断。
- [ ] Mock 契约测试覆盖：正常五状态、HTTP 200 业务拒绝、非 JSON、缺失 verdict、未知 verdict、401、响应超时。后三类协议／传输故障不轮询直到超时再猜测。
- [ ] GET 对约定瞬时故障最多 3 次总尝试；POST 提交 1 次。通过 Mock 请求计数断言提交超时也只接收一次；禁止仅 mock `requests.post` 来证明端到端次数。
- [ ] 执行 `python -m pytest tests/unit/test_judge_oracle.py tests/integration/test_local_adapter.py tests/integration/test_retry_policy.py -q`，再运行当前全部非 e2e 测试。
- [ ] 提交 `fix: enforce explicit OJ result contracts` 并推送。

**验收**：原审计中的“预期错误但实际 AC／401／断网均通过”全部消失，错误原因能沿执行链传到结果。

## S03：统一配置、入口和退出码

**文件**：新增 `config_center/models.py`、`tests/unit/test_task_config.py`、`tests/integration/test_entrypoints.py`；修改 `task_center/models.py`、`config_center/config.py`、`backend/app.py`、`backend/routers/task_router.py`、`main.py`。

**接口**：`TaskConfig` 与独立 `ExecutionCredentials`；`load_task_config(config_path, env, overrides) -> TaskConfig`；`create_app(config_path=None)` 在 lifespan 初始化、关闭服务，不能 import 时启动任务；`cli_exit_code(summary) -> int`。

- [ ] 先写 `test_empty_strategies_rejected/test_unknown_strategy_rejected/test_zero_count_rejected/test_zero_cases_never_exit_zero/test_config_path_is_used/test_env_timeout_is_numeric`。

```python
import pytest
from pydantic import ValidationError
from config_center.models import TaskConfig

@pytest.mark.parametrize("strategies,count", [([], 1), (["unknown"], 1), (["random"], 0)])
def test_invalid_generation_request(strategies, count):
    with pytest.raises(ValidationError):
        TaskConfig(adapter_name="local_oj", base_url="http://127.0.0.1:8099",
                   profile_id="a_plus_b", problem_id=1,
                   strategies=strategies, case_count=count)
```

- [ ] `python -m pytest tests/unit/test_task_config.py tests/integration/test_entrypoints.py -q` 红测；按设计优先级合并配置并校验。API 非法配置返回 422，CLI 返回 2；登录失败／零执行结果返回 1。
- [ ] 用 `with TestClient(create_app(config_path=...))` 测不同配置文件和启动／关闭，不读取用户真实密码；CLI 用 subprocess 调用，检查真实 returncode，不能只测退出码辅助函数。
- [ ] `--mode concurrent` 在 S06 接通前明确报“功能尚未启用”并非零退出；不得悄悄退回顺序。配置模型先支持该字段，能力门禁放在入口。
- [ ] 绿测、检查原 CLI 参数兼容后提交 `fix: reject invalid and empty task runs` 并推送。

## S04：让 YAML 真正决定题目和用例

**文件**：新增 `config_center/profile_loader.py`、`profiles/a_plus_b.yaml`、`profiles/max_of_two.yaml`、`profiles/templates/a_plus_b/*.cpp`、`profiles/templates/max_of_two/*.cpp`；修改四个 case generator／builder 和 TestCase；测试 `tests/unit/test_profiles.py`、`tests/unit/test_case_generation.py`。

**接口**：`ProfileLoader(root: Path).load(profile_id) -> ProblemProfile`；`CaseBuilder.build(config: TaskConfig, profile: ProblemProfile) -> list[TestCase]`。生成器仅消费 profile、rng 和分配数量，不访问网络。新增 pytest fixtures `task_config/profile/built_cases`，分别返回有效 TaskConfig、a_plus_b profile 及生成结果，供后续阶段复用。

- [ ] 红测定义相同 seed 的真实源码／预期完全相同；换 seed 对一组含多个候选模板的 profile 至少产生一种不同顺序；两道题不得仍生成同一套 A+B 程序。

```python
def test_profile_and_seed_determine_cases(task_config, profile):
    from core_engine.case_engine.case_builder import CaseBuilder
    first = CaseBuilder().build(task_config, profile)
    second = CaseBuilder().build(task_config, profile)
    assert len(first) == task_config.case_count
    assert [(c.source_sha256, c.expectation) for c in first] == [
        (c.source_sha256, c.expectation) for c in second]
    assert {c.strategy for c in first} == set(task_config.strategies)
```

- [ ] `python -m pytest tests/unit/test_profiles.py tests/unit/test_case_generation.py -q` 确认红测。实现 YAML schema；题号来自任务运行绑定，profile_id 表示题目逻辑，两者不可混为一谈。
- [ ] 首个 profile 按下面的结构落地；max_of_two 采用相同 schema，但正确解、错误解和 fixture 均使用求最大值逻辑。

```yaml
schema_version: 1
id: a_plus_b
title: A plus B
language: cpp
fixtures:
  - {stdin: "1 2\n", stdout: "3\n"}
  - {stdin: "-1 1\n", stdout: "0\n"}
strategies:
  random:
    templates:
      - {path: templates/a_plus_b/ac.cpp, expected_verdict: AC}
      - {path: templates/a_plus_b/wa.cpp, expected_verdict: WA}
  boundary:
    templates:
      - {path: templates/a_plus_b/invalid_syntax.cpp, expected_verdict: CE}
  rule:
    scenarios:
      - {name: unauthenticated, auth_mode: anonymous,
         expectation: {kind: http_error, http_status: 401}}
```

- [ ] profile 另补 CE/TLE/RE 模板供全状态验收；RE 用确定触发异常的程序，TLE 用持续循环，真实结论在 S10 获得。规则还覆盖不存在题号和空源码，分别映射 `PROBLEM_NOT_FOUND` 与 `CODE_REQUIRED`。空源码当前会被业务层拒绝，不能期望 CE；CE 模板必须非空且语法错误。不要声称当前 OJ 支持实际上没有实现的语言校验。
- [ ] 每个模板路径 resolve 后必须位于 profiles 根目录，拒绝 `../` 和绝对路径；未知策略、缺模板、schema 错误、零用例全部立即失败。保存 profile／源码哈希、seed、auth_mode 和请求覆盖内容。
- [ ] 校验最终数量等于 case_count、每个策略至少一例，匿名规则不复用已登录 Cookie。全部测试通过后提交 `feat: generate cases from problem profiles` 并推送。

**验收**：新增第二道题仅增加 profile 和模板，执行器无需按题目写分支；报告输入的含义遵守设计文档。

## S05：持久化任务，并让重启后的历史可信

**文件**：新增 `storage/__init__.py`、`storage/database.py`、`storage/repository.py`、`storage/migrations/001_initial.sql`、`task_center/service.py`、`task_center/runtime.py`；修改 TaskManager、任务／报告路由和 main；新增 `tests/unit/test_repository.py`、`tests/integration/test_task_lifecycle.py`、`tests/integration/test_restart_recovery.py`。

**接口**：

```python
TaskRepository(db_path: Path)
repo.initialize() -> None
repo.insert_task(config, profile, cases, platform_sha: str, sut_sha: str | None) -> str
repo.get_task(task_id: str) -> TaskRecord
repo.list_cases(task_id: str) -> list[StoredCase]
repo.save_case_result(task_id: str, result: CaseResult) -> None
repo.transition(task_id: str, allowed_from: set[str], target: str) -> bool
repo.recover_interrupted() -> int

TaskService(repo, profile_loader, adapter_factory, report_root: Path)
service.start() -> None  # 获取运行锁，恢复历史，启动单个任务队列消费者
service.create(config, credentials) -> str
service.get(task_id) -> TaskRecord
service.wait(task_id, timeout: float) -> TaskRecord
service.cancel(task_id) -> None
service.close() -> None
```

S05 用顺序执行器；CaseResult 在此阶段扩展为包含 case_id、assertion_status、observation、reason、时间戳、duration_ms、attempt_count 的完整记录。

- [ ] **S05a 存储红测**：先断言新建 repository 对同一 DB 可读出输入，且密码不存在。tmp_path DB 独立于真实历史。

```python
from storage.repository import TaskRepository

def test_inputs_survive_new_repository(tmp_path, task_config, profile, built_cases):
    db = tmp_path / "tasks.db"
    first = TaskRepository(db)
    first.initialize()
    task_id = first.insert_task(task_config, profile, built_cases, "test-sha", None)
    reopened = TaskRepository(db)
    reopened.initialize()
    assert reopened.get_task(task_id).id == task_id
    saved = reopened.list_cases(task_id)
    assert [c.source_sha256 for c in saved] == [c.source_sha256 for c in built_cases]
```

- [ ] `python -m pytest tests/unit/test_repository.py -q` 确认红测；创建四表、外键、迁移和短事务。写入全部输入失败时不允许发出任何 OJ 请求；每条结果保存幂等，不累计两次。
- [ ] 绿测后独立提交 `feat: add SQLite task repository`。
- [ ] **S05b 服务红测**：加入“进程 A 保存后退出，进程 B 读回”“模拟崩溃后的活动任务 INTERRUPTED”“第二写进程拿锁失败但不修改任务”“已完成历史不变”“账号密码未进入 DB 字段与 JSON”的 subprocess 测试。
- [ ] 用操作系统文件锁实现单运行进程，Windows／Linux 分别封装系统锁并验证进程退出后释放，禁止只写 PID 文件；通过 lifespan 调用 start/close。`service.create` 调用 profile builder，先原子保存任务与实际输入再入队；队列消费者只消费已保存的输入快照。凭据保存在 runtime 内存字典，终态清理。
- [ ] 接入 v1 创建／历史／详情接口和 CLI；其结果只读同一个 repository，旧路由委托同一服务。FAILED 和 COMPLETED 按设计区分，CLI success 使用所有条件。
- [ ] 执行 `python -m pytest tests/unit/test_repository.py tests/integration/test_task_lifecycle.py tests/integration/test_restart_recovery.py -q`；对活动任务删除返回 409、未找到返回 404、分页 limit 上限做断言。
- [ ] 独立提交 `feat: persist task lifecycle across restarts`，分别推送两次提交并记录远端 SHA。

**验收**：真实新进程能读回配置／实际源码／结果；活动任务中断不会伪装成功；数据库内没有可用于恢复登录的密码或 Cookie。

## S06：接通并发，并验证取消确实停止调度

**文件**：修改 `plugins/plugin_manager.py`、`core_engine/executor/{task_executor,sequential_executor,concurrent_executor}.py`、`task_center/runtime.py`、`task_center/service.py`；新增 `tests/integration/test_concurrency.py`、`tests/integration/test_cancellation.py`。

**接口**：`PluginManager.create_adapter(name, base_url, request_timeout) -> BaseOJAdapter` 每次新实例；执行器 `run(cases, credentials, cancel_event, on_case_result) -> RunSummary`。TaskService 接收 adapter_factory；worker 用自己的 Adapter 并在 finally close。匿名用例使用独立无 Cookie 请求上下文。

- [ ] **S06a 红测**：用 Mock 阻塞屏障证明并发重叠；相同 base_url 下两次工厂调用不能返回同一实例。

```python
def test_adapter_factory_does_not_cache_sessions(mock_oj):
    from plugins.plugin_manager import PluginManager
    manager = PluginManager()
    a = manager.create_adapter("local_oj", mock_oj.base_url, 2)
    b = manager.create_adapter("local_oj", mock_oj.base_url, 2)
    try:
        assert a is not b
    finally:
        a.close()
        b.close()
```

- [ ] 实现最多 max_workers 个在途 future，完成一个再补一个；不能一次性把 1000 个任务全 submit 到线程池。使用 `wait(..., return_when=FIRST_COMPLETED)` 的有界循环，取消时停止补位。登录失败留下明确用例 ERROR 和任务失败原因。
- [ ] `test_concurrent_requests_overlap` 用 Mock Event 等待至少两个请求进入，再 release；断言 `2 <= max_active_submissions <= max_workers`，而顺序模式等于 1。并发不是比较一次运行快了多少秒。
- [ ] `test_results_do_not_cross_cases` 让不同用例延迟、结果不同，断言每个 case_id 的实际结果和请求源码对应；`test_anonymous_rule_has_no_cookie` 检查 Mock 日志中该请求没有 Cookie。
- [ ] 通过后移除 S03 的并发能力门禁，提交 `feat: isolate adapters and enable bounded concurrency`。
- [ ] **S06b 红测**：Mock 挂住首批请求，调用 cancel，记录此刻已接收的提交数，释放在途请求后不得出现新的提交；终态必须 CANCELLED，即便在途请求全部 AC。finally 总是 release，避免测试挂死。
- [ ] 实现取消状态的条件更新、Ctrl+C 触发 Event、关机宽限期、结果逐条保存；活动任务上限／队列 20 满载返回 429。UI 查询能看见中间进度。
- [ ] 执行 `python -m pytest tests/integration/test_concurrency.py tests/integration/test_cancellation.py -q`，再执行全部非 e2e 回归；提交 `fix: make cancellation stop further submissions` 并推送。

**验收**：顺序和并发路径都经过公共入口；终态计数满足 total=passed+failed+error+cancelled；不宣称已经终止远端程序。

## S07：让报告足以复现失败

**文件**：修改 `core_engine/report_engine/report_generator.py`、`backend/routers/report_router.py`；新增 `tests/unit/test_reports.py`、`tests/integration/test_report_endpoints.py`。

**接口**：`ReportGenerator(root: Path).generate(task_snapshot) -> list[ReportArtifact]`；Artifact 含 `id, format, relative_path, sha256`。task_snapshot 从 repository 读取，包括 config/profile/cases/results；生成器不从 `_last_judge_result` 或内存统计拼报告。

- [ ] 红测通过 fixture `failed_task_snapshot` 构造一条源码含 `<script>alert(1)</script>`、实际 WA、预期 AC、错误文本包含模拟秘密的结果。fixture 定义在本阶段 `tests/conftest.py`，不是硬编码为输出相同的实现。

```python
def test_html_escapes_code_and_reports_reason(tmp_path, failed_task_snapshot):
    from core_engine.report_engine.report_generator import ReportGenerator
    artifacts = ReportGenerator(tmp_path).generate(failed_task_snapshot)
    html = next(a for a in artifacts if a.format == "html")
    body = (tmp_path / html.relative_path).read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
    assert "AC" in body and "WA" in body
    assert "test-secret-must-not-leak" not in body
```

- [ ] `python -m pytest tests/unit/test_reports.py -q` 先红；实现统一 JSON schema、HTML 转义、字段白名单和已知秘密替换。日志、报告、异常消息共用脱敏函数。
- [ ] 同一秒生成两次报告路径必须不同；写入临时文件后原子替换；写盘失败标记任务报告阶段失败，不留下数据库指向不存在文件的成功记录。
- [ ] JSON 和 HTML 均包含全部失败输入、expected/actual/reason、seed、source/profile 哈希、task_id、平台和被测版本。统计字段统一 `error`。
- [ ] 接口仅接收 task_id 和 html/json，通过 repository 找文件；增加路径穿越、报告不存在、下载内容及 Content-Type 检查。
- [ ] 执行 `python -m pytest tests/unit/test_reports.py tests/integration/test_report_endpoints.py -q`，绿测后提交 `feat: generate traceable safe test reports` 并推送。

## S08：补齐 Web 的可用流程

**文件**：修改 `frontend/index.html`、`backend/routers/task_router.py`、`backend/routers/config_router.py`；新增 `tests/integration/test_web_api_contract.py`、`docs/manual-web-checks.md`。

**接口**：只使用设计文档的 v1 API。页面展示 profile、真实题号、策略、数量、seed、mode/max_workers；历史详情展示配置／源码／预期实际／错误和报告。

- [ ] 红测 `test_create_returns_202_and_location/test_history_contains_snapshot/test_cancel_terminal_returns_409/test_frontend_summary_uses_error`；TestClient 必须在上下文管理器中运行。
- [ ] 后端契约检查示例使用完整 `valid_task_payload` fixture（在本阶段定义，账户仅为 Mock 测试账户）：

```python
def test_create_task_contract(client, valid_task_payload):
    response = client.post("/api/v1/tasks", json=valid_task_payload)
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    detail = client.get(f"/api/v1/tasks/{task_id}")
    assert detail.status_code == 200
    assert "password" not in detail.text
```

- [ ] 页面选择顺序模式时隐藏／禁用 worker 输入且发1；任务活动时禁用删除，取消后显示 CANCEL_REQUESTED；展示具体 HTTP 错误，不只 toast “失败”。动态源码／错误文本用 textContent。
- [ ] 运行 `python -m pytest tests/integration/test_web_api_contract.py -q`，再启动平台与 Mock，手动验收：创建顺序任务→看进度→查看失败详情→下载两种报告→创建并发任务→取消→刷新→重启→历史仍在。
- [ ] 把步骤、任务 ID、真实结果和截图存入本次证据，标明哪些是人工 UI 验证。未操作页面不得写成 Web 已验收。
- [ ] 提交 `feat: expose task controls and history in web UI` 并推送。

## S09：Docker 交付先用 Mock 跑通

**文件**：新增 `Dockerfile`、`.dockerignore`、`compose.yaml`、`.env.example`、`scripts/smoke_compose.py`、`docs/docker.md`；可复用 `tests/mock_oj/server.py` 为演示服务。

**接口**：Compose 服务 `platform/mock-oj/smoke`；mock-oj 和 smoke 放在 `demo` profile；platform 单 Uvicorn worker，对外 8000，容器内 `/data` 用命名卷存 SQLite 和报告。mock-oj 8099。smoke 在同一网络通过 HTTP 运行平台任务。

- [ ] 先定义 smoke 断言：平台 health 200；创建含一个预期 AC 和一个预期拒绝的 Mock 任务；最终 passed=total>0；下载 JSON／HTML；保存 task_id 供重启检查。缺接口时脚本应退出非零。
- [ ] smoke 脚本参数固定为 `--phase create|verify --platform-url http://platform:8000 --evidence /evidence/smoke.json`；create 写任务 ID／报告 SHA，verify 查询同一 ID 并断言报告 SHA 不变。等待必须有截止时间，超时退出1。
- [ ] 镜像采用 Python 3.12、锁定依赖、非 root 用户；生产镜像不包含 token、历史 reports、.git 或开发 venv。Mock 可使用独立构建 target 复制测试服务。
- [ ] 先确认 Docker Desktop Linux 引擎运行；以下命令在实施时执行，本轮不执行。

```powershell
docker compose --profile demo config
docker compose --profile demo up -d --build
docker compose --profile demo run --rm smoke --phase create
docker compose restart platform
docker compose --profile demo run --rm smoke --phase verify
docker compose logs --no-color platform
```

- [ ] 持久卷还需验证普通 `docker compose down` 后再 up，verify 仍成功。不得用 `down -v` 验证持久化；清理测试数据另列为明确操作。
- [ ] 保存镜像标识、容器 health、smoke JSON、退出码。通过后提交 `build: containerize platform and mock demo` 并推送；引擎未连接标 BLOCKED。

## S10：以真实 C++ OJ 验收简历中的判题能力

**文件**：新增 `infra/cpp-oj.Dockerfile`、`compose.e2e.yaml`、`scripts/prepare_sut.ps1`、`scripts/seed_e2e.py`、`scripts/cleanup_e2e.py`、`tests/e2e/test_real_oj.py`、`docs/e2e.md`、`config_center/e2e.example.yaml`。

**接口**：`prepare_sut.ps1` 将固定提交下载到忽略目录 `.cache/cpp-oj` 并核验 HEAD；Compose 使用该内容构建 Linux C++ 服务及专用 MySQL。seed 输出 `artifacts/e2e-fixtures.json`，含 run_id、精确题目 ID、profile 对应关系和内容哈希；cleanup 只清除此清单创建的数据。

- [ ] 检查固定提交的源码、构建依赖、登录协议、判题字段、MySQL schema 及测试数据格式；根据事实编写镜像。已有文档可能过时，不能以 HTTP 200 推断服务正确。
- [ ] 写 E2E 参数矩阵；此时用缺少目标配置的显式 e2e 运行验证门禁确实失败，不将它算作产品缺陷。

```python
import pytest

@pytest.mark.e2e
@pytest.mark.parametrize("profile_id", ["a_plus_b", "max_of_two"])
@pytest.mark.parametrize("mode", ["sequential", "concurrent"])
@pytest.mark.parametrize("verdict", ["AC", "WA", "CE", "TLE", "RE"])
def test_real_verdict(real_oj_runner, profile_id, mode, verdict):
    result = real_oj_runner.run_single_verdict(profile_id, mode, verdict)
    assert result.observation.verdict == verdict
    assert result.assertion_status == "PASSED"
```

`real_oj_runner` fixture 由本阶段实现：读取 fixture 清单绑定真实题号，以公共 TaskService 发起任务，通过 repository 取回唯一用例结果。并发单用例矩阵只证明入口一致；另设含至少5条用例的批量并发测试证明重叠及结果对应。

- [ ] seed 必须使用专用数据库／容器，创建带唯一 run_id 的两道题及明确 stdin/stdout；若 API 不返回 ID，按唯一标题精确查询并校验内容，不用 `MAX(id)` 猜测。不使用共享环境的旧 pytest seed。
- [ ] 两道题均配置足以区分 AC 和 WA 的 fixture；CE 用不可编译源码，RE 用明确异常退出，TLE 用无限循环。每条保留实际响应和题目限制，不能用 Mock 强制 verdict。
- [ ] 测真实登录失败、匿名拒绝、缺失题目、批量顺序／并发、取消边界；并发可能暴露 C++ 问题，需单独归因，不在 Adapter 中篡改结果让测试过。
- [ ] 执行：

```powershell
powershell -NoProfile -File scripts/prepare_sut.ps1
docker compose -f compose.e2e.yaml up -d --build
python scripts/seed_e2e.py --config config_center/e2e.example.yaml --ledger artifacts/e2e-fixtures.json
python -m pytest tests/e2e --run-e2e -q --junitxml=artifacts/e2e.xml
python scripts/cleanup_e2e.py --ledger artifacts/e2e-fixtures.json
```

- [ ] example 配置只含隔离环境非秘密参数；数据库密码和管理员密码从环境读取。执行前验证目标 Compose 项目标识和 DB 名，不把示例名当真实连接证明。cleanup 后按精确 ID 读回确认删除，并保留清单用于失败恢复。
- [ ] 通过后提交 `test: verify platform against pinned cpp OJ` 并推送；基础设施不满足则标 BLOCKED，继续可独立完成的 S11 Mock CI。

**验收**：两道题、五种真实状态、两种执行入口、批量并发都留下证据。若需修改 C++，在其独立仓库另做提交／验证，并更新固定 SHA；不能悄悄改变被测版本。

## S11：让 GitHub Actions 真正运行并归档

**文件**：新增 `.github/workflows/regression.yml`、`scripts/check_evidence.py`、`docs/ci.md`；更新测试依赖锁和 README 状态链接。

**前提（已完成仓库准备）**：用户授权创建的 GitHub 私有仓库为 `https://github.com/zhzgg123-pixel/oj-test-platform`，已核实 Actions 启用并同步 S09 main。Gitee 继续作为 origin；GitHub 使用名为 github 的第二远端。后续按同一提交运行 CI，仍需实际工作流和制品证据，不能仅凭仓库存在标记通过。

**接口**：工作流运行 `python -m pytest -m "not e2e" --junitxml=artifacts/junit.xml`；`check_evidence.py` 解析 JUnit，要求 tests>0、failures=0、errors=0，并检查指定报告存在且 JSON total>0。它还记录平台 SHA 与运行环境，不允许仅创建空 HTML 冒充制品。

- [ ] 红测 `tests/unit/test_evidence_gate.py` 覆盖零用例、缺报告、失败 XML、全通过 XML；脚本错误返回1。先本地跑通，再接入工作流。
- [ ] workflow 设置 push、pull_request、workflow_dispatch；permissions 为 contents:read；Python 矩阵 3.12/3.14；缓存键包括依赖锁哈希。Actions 引用实施时核验官方版本并固定完整提交 SHA，避免把示例版本直接视作当前安全版本。
- [ ] 测试后使用 `if: always()` 归档 JUnit 和演示任务真实生成的 HTML／JSON，`if-no-files-found: error`；生成演示报告失败必须保留非零退出码，不能用 `|| true`。单独保留 pytest 步骤和报告生成步骤，防止某步失败遮蔽另一层证据。
- [ ] Docker smoke 独立 job；S10 完成后增加隔离 C++ E2E job，失败时归档脱敏日志及清单。私有 SUT clone 凭据通过受控 CI secret 注入，不直接写 YAML；fork PR 无 secret 时该 E2E 作业状态必须明确，不算真实联调通过。
- [ ] 在对应 GitHub 分支运行，记录 run URL 和 commit SHA，与 Gitee 同一提交核对；下载 artifacts，打开 HTML 并解析 JSON 验证非空。
- [ ] 在独立验证分支制造一条确定失败的测试，证明工作流红且报告仍归档；修复／恢复后再跑绿色。不要把故意失败提交合入 main。
- [ ] 提交 `ci: run regression and archive test evidence` 并推送 Gitee。只有 GitHub 实际 run 和制品验收通过后才能把此项标 PASS。

## S12：整理交付和简历证据

**文件**：更新 `README.md`、`OJ测试开发工具.md`；新增 `docs/acceptance.md`、`docs/troubleshooting.md`、`docs/evidence/index.json`。

- [ ] README 按真实命令记录安装、配置、Web、CLI、Mock、Docker、真实 OJ、CI 七个入口；分别说明平台 SQLite 和 OJ MySQL 的职责。清除原文档中“尚未实现”与“已完成”的自相矛盾描述。
- [ ] acceptance 对照设计文档每一条简历要求，填写具体文件、测试节点、最后验证 SHA、环境、PASS/FAIL/BLOCKED/NOT_RUN、制品位置。
- [ ] 用一份干净检出重新安装，运行全部非 e2e 测试、Docker smoke；在可用环境执行真实 e2e。已有绿测后没有改动的阶段不反复扩大测试范围；此处是交付安装验收。
- [ ] 核实数据库新进程历史、失败复现、负向断言、取消、会话隔离、报告脱敏、远端 SHA、GitHub 制品。任何 BLOCKED 保留，不写成“全栈全部通过”。
- [ ] 文档提交 `docs: publish verified platform acceptance evidence`，推送并读回。只有完整验收通过才创建交付标签 `v1.0.0`，记录标签指向的提交，不以标签替代证据。

## 每一步的提交、推送与回退约定

下面是实施时的检查清单，不是本轮已经执行的命令：

1. 从干净的当前 main 创建该阶段分支，例如 `step/02-result-contracts`。保留用户未提交改动，不用 reset --hard 或 clean 清理。
2. 先记录本阶段原始失败；实现后运行该阶段测试，再运行现有非 e2e 回归。生成的临时报告和数据库不进 Git。
3. 按本阶段 Files 清单显式 git add；`git diff --cached --check` 和差异审查通过才提交。S05/S06 分子提交。提交主题使用阶段表中的实际英文主题。
4. 推送该阶段分支，记录本地 HEAD 与远端分支 SHA 相同。main 用快进合并或经审核的 PR 合并；不 force push，不把失败测试标记 skip 来过关。
5. 每阶段在 `docs/evidence/index.json` 追加一条脱敏摘要；完整日志留在 artifacts／CI 制品中。日志含 git SHA、命令、环境和退出码，不能只填“测试通过”。

```powershell
git status --short
git diff --cached --check
python -m pytest -m "not e2e" -q
git push -u origin HEAD
git rev-parse HEAD
git ls-remote origin "refs/heads/$(git branch --show-current)"
```

执行者必须在 commit 之前完成测试，上面 push 前的回归用于确认最终暂存版本。测试输出为 no tests collected 时不能提交为已验收。

回退使用针对本阶段提交的 `git revert` 并重新验收；SQLite schema 变更前先备份本地数据。代码回退不自动降级数据库，优先保持向后兼容的增量迁移；未验证降级时恢复备份或使用新的隔离数据库，不删除用户历史。

## 每步给用户的完成报告模板

```text
阶段：S02 判定和 Adapter
改动：具体行为及涉及文件
验证：命令、通过数量、关键负向用例
证据：日志／报告位置；Mock 或真实 OJ 标识
提交：本地 SHA、Gitee 分支／URL、远端读回 SHA
状态：PASS / FAIL / BLOCKED / NOT_RUN
后续：下一阶段与尚未满足的前提
```

## 计划自检结果

- 简历映射表所有能力均有对应阶段；额外正确性缺陷分别落在 S02/S03/S06/S07。
- 输入含义与现有 OJ 协议一致，不把模板随机采样说成任意 stdin 注入。
- TaskConfig、TaskService、Oracle、Repository、报告契约统一；SQLite 和 C++ MySQL 没有混用。
- 每阶段均有明确文件、行为、验证和提交边界；Mock、Docker、真实联调、CI 结论分开。
- 实施第一步为 S00。后续用户指定阶段后按本计划执行；本轮不创建分支或推送代码。
