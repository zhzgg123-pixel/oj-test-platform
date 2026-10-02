# OJ 在线判题系统自动化测试平台

> **项目定位**：面向 OJ 系统的工程化自动化测试平台
> **面向人群**：测试开发 / 测试自动化 / 测试平台方向求职（秋招）
> **核心原则**：不是测试脚本，不是 demo，不是单纯 pytest 项目 —— 是工程化测试平台系统

---

## 目录

- [一、项目背景](#一项目背景)
- [二、项目目标](#二项目目标)
- [三、系统整体架构](#三系统整体架构)
- [四、系统模块设计](#四系统模块设计)
- [五、数据流设计](#五数据流设计)
- [六、非功能性要求](#六非功能性要求)
- [七、开发路线图](#七开发路线图)
- [八、项目定位说明](#八项目定位说明)
- [九、面试指南](#九面试指南)
- [附录](#附录)

---

## 一、项目背景

为提升 OJ 系统测试效率与自动化能力，构建一套 **OJ 自动化测试平台**。

该平台用于对在线判题系统进行：

- **功能测试** —— 验证注册、登录、提交判题等核心功能
- **接口测试** —— 验证 OJ 各 API 的正确性与健壮性
- **回归测试** —— 代码变更后自动验证已有功能不受影响
- **批量测试** —— 一次性执行大量测试用例，覆盖各种场景
- **测试结果分析** —— 自动生成报告，分析通过率、失败分布

区别于传统测试脚本，本项目为 **工程化测试平台系统**。

---

## 二、项目目标

构建一个具备以下能力的测试平台：

| # | 能力 | 说明 | 阶段 |
|---|------|------|:----:|
| 1 | OJ 系统自动化测试 | 自动登录、提交代码、获取判题结果 | ✅ 已完成 |
| 2 | 测试用例自动生成 | 随机 / 边界 / 规则三种策略 | ✅ 已完成 |
| 3 | 测试任务调度执行 | 后台异步执行，提交即返回 | ✅ 已完成 |
| 4 | 测试结果自动校验 | Oracle 规则引擎判定 AC/WA/TLE/RE | ✅ 已完成 |
| 5 | 测试报告生成与展示 | HTML + JSON 双格式 | ✅ 已完成 |
| 6 | 插件化适配多 OJ 系统 | BaseAdapter + PluginManager | ✅ 已完成 |
| 7 | Web 可视化操作界面 | 浏览器操作，非技术人员可用 | ✅ 已完成 |
| 8 | 配置化运行与环境切换 | YAML 多环境 + 环境变量覆盖 | ✅ 已完成 |
| 9 | 平台自身质量保障 | pytest + Mock OJ Server + 日志 | 🔜 进行中 |
| 10 | 容器化部署 | Docker + docker-compose | 🔜 进行中 |
| 11 | CI/CD 集成 | GitHub Actions 自动测试 | 🔜 进行中 |
| 12 | 任务持久化 | SQLite 存储任务记录 | 📋 待实现 |
| 13 | 前后端分离 | Vue3 + Element Plus | 📋 待实现 |
| 14 | 分布式扩展 | Redis + Celery 扩展方案 | 📐 架构设计 |
| 15 | AI 辅助测试 | LLM 辅助生成测试点（可选） | 💡 探索中 |

---

## 三、系统整体架构

### 四层架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Web UI)                         │
│           HTML + JS / Vue3 / 任务管理 / 结果展示             │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP REST API
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Backend (FastAPI 服务层)                     │
│       REST API / 任务接收 / 配置管理 / 报告查询 / CORS        │
│    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│    │ 任务路由  │  │ 配置路由  │  │ 报告路由  │  │ 插件路由  │  │
│    └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ 内部调用
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                Core Engine (测试核心引擎)                     │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │case_engine│ │api_client│ │ executor │ │  assertion   │  │
│  │ 用例生成  │ │ 接口封装  │ │ 执行引擎  │ │  结果校验    │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │
│  ┌──────────┐                                              │
│  │report_eng│                                              │
│  │ 报告生成  │                                              │
│  └──────────┘                                              │
└──────────────────────────┬──────────────────────────────────┘
                           │ 调用插件适配
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Plugins (OJ 适配层)                       │
│                                                             │
│  ┌────────────────────────────┐  ┌──────────────────────┐  │
│  │   BaseOJAdapter (抽象层)   │  │  PluginManager       │  │
│  └───────────┬────────────────┘  │  (插件管理器/加载器)  │  │
│              │ 继承实现           └──────────────────────┘  │
│  ┌────────────────────────────┐                              │
│  │   LocalOJAdapter           │  ← cpp-oj 适配器            │
│  └────────────────────────────┘                              │
│  ┌────────────────────────────┐                              │
│  │   SchoolOJAdapter (示例)   │  ← 可扩展：学校 OJ          │
│  └────────────────────────────┘                              │
└─────────────────────────────────────────────────────────────┘

           ┌──────────────┐  ┌──────────────┐  ┌──────────┐
           │ Config Center │  │ Task Center  │  │ Database │
           │  (配置中心)    │  │  (任务调度)   │  │ (SQLite) │
           └──────────────┘  └──────────────┘  └──────────┘
```

### 为什么不做单纯 pytest 项目？

pytest 解决的是测试执行问题，而企业中还需要：

- **任务管理**：测试任务何时创建、执行中还是已完成？
- **配置管理**：不同环境（dev/staging/prod）怎么切换？
- **报告管理**：历史报告在哪里看？
- **多系统适配**：不同 OJ 接口差异怎么屏蔽？

所以将测试执行能力抽象成 Core Engine，通过 FastAPI 提供服务化接口，通过 Adapter 支持插件化扩展。这是测开思维和脚本思维的区别。

---

## 四、系统模块设计

### 1. Core Engine - case_engine（用例生成器）

**职责**：根据策略自动生成 OJ 测试用例，输出统一 TestCase 模型。

**采用策略模式，支持三种生成策略**：

| 策略 | 类名 | 说明 |
|------|------|------|
| 随机生成 | `RandomGenerator` | 从代码模板池随机选取，覆盖 AC/CE/WA/TLE |
| 边界值生成 | `BoundaryGenerator` | 基于 BVA 生成边界场景 |
| 规则生成 | `RuleGenerator` | 基于业务规则模板构造 |

```python
@dataclass
class TestCase:
    id: str
    desc: str
    problem_id: str
    code: str
    lang: str = "cpp"
    expected_status: str = "AC"
    tags: list[str] = field(default_factory=list)
    priority: str = "P1"

class BaseGenerator(ABC):
    @abstractmethod
    def generate(self, spec: dict) -> list[TestCase]: ...

class CaseBuilder:
    """组合多策略，按 P0→P1→P2 排序输出"""
    def build(self, spec: dict) -> list[TestCase]: ...
```

**面试可讲**：
> 我设计了基于策略模式的测试用例生成模块，RandomGenerator 随机覆盖各种判题结果，BoundaryGenerator 进行边界值分析，RuleGenerator 基于业务规则构造异常场景。通过 CaseBuilder 组合多策略，可以在一次执行中覆盖正常、边界、异常三类测试场景。

---

### 2. Core Engine - api_client（接口封装）

**职责**：封装 OJ 系统的 HTTP 接口，提供统一的调用方式。

```python
class RequestClient:
    def __init__(self, base_url, timeout=30, retry_count=3, retry_delay=1.0): ...
    def get(self, path, **kwargs): ...
    def post(self, path, data=None, json=None, **kwargs): ...
    def get_session_id(self) -> Optional[str]: ...
    def clear_session(self): ...
```

**要点**：requests.Session 管理 Cookie、5xx 自动重试、统一超时和异常处理。

---

### 3. Core Engine - executor（执行引擎）

**职责**：批量执行测试用例，自动提交代码并获取判题结果。

| 执行器 | 策略 | 适用场景 |
|--------|------|----------|
| `SequentialExecutor` | 顺序执行 | 单用例调试、小批量 |
| `ConcurrentExecutor` | 并发执行（ThreadPoolExecutor） | 大批量测试、性能测试 |

```python
@dataclass
class CaseResult:
    case: TestCase
    status: str = "PENDING"       # PENDING / RUNNING / PASSED / FAILED / ERROR
    actual_status: str = ""
    judge_result: Optional[JudgeResult] = None
    error_message: str = ""
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration(self) -> float: ...
    @property
    def passed(self) -> bool:

@dataclass
class TaskResult:
    total: int = 0
    passed: int = 0
    failed: int = 0
    error: int = 0
    case_results: list[CaseResult] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def pass_rate(self) -> float: ...
    @property
    def duration(self) -> float: ...
```

**设计要点**：
- 支持同步判题和异步判题两种 OJ 模式
- `expected_status="ERROR"` 特殊语义：预期出错的用例，任何异常均算通过
- ConcurrentExecutor 采用 ThreadPoolExecutor，max_workers 可配置，各用例独立提交互不阻塞

---

### 4. Core Engine - assertion（结果校验）

**职责**：判题结果自动校验，对应测试中的断言机制。

```python
class JudgeOracle:
    """Oracle 规则引擎 - 将判题规则集中管理"""

    RULES: dict[str, dict] = {
        "AC":  {"check": lambda r: r.get("passed", 0) > 0 and r.get("passed") == r.get("total"),
                "desc": "全部测试用例通过"},
        "WA":  {"check": lambda r: r.get("passed", 0) < r.get("total", 1),
                "desc": "输出结果与预期不符"},
        "CE":  {"check": lambda r: bool(r.get("compile_msg", "")),
                "desc": "编译错误"},
        "TLE": {"check": lambda r: r.get("time_used_ms", 0) >= 1000,
                "desc": "运行超时"},
        "RE":  {"check": lambda r: r.get("exit_code", 0) != 0,
                "desc": "运行时错误"},
        "MLE": {"check": lambda r: r.get("memory_used_kb", 0) >= 65536,
                "desc": "内存超限"},
    }

    def verify(self, judge_result, expected_status) -> OracleResult: ...
    @classmethod
    def register_rule(cls, status, check_func, desc=""): ...
```

**面试可讲**：
> 普通的测试工具直接用 `if result == "AC"` 做断言，我设计了一个规则引擎，每个判题状态对应一条规则，校验时根据预期状态查找对应规则执行断言。新增状态只需加一条 lambda，扩展性比硬编码好很多。

---

### 5. Core Engine - report_engine（报告系统）

**职责**：测试完成后生成结构化报告。

```python
class ReportGenerator:
    def generate(self, task_result: TaskResult, task_config=None) -> dict:
        """JSON + HTML 双格式"""
    def list_reports(self) -> list[dict]: ...
```

**报告内容**：通过率、状态分布统计、失败用例详情、全部用例列表。

---

### 6. Plugins（插件系统）

**职责**：通过适配器模式，屏蔽不同 OJ 系统的接口差异。这是本平台最核心的设计之一。

| 组件 | 职责 |
|------|------|
| `BaseOJAdapter` | 抽象基类，定义接口契约 |
| `LocalOJAdapter` | cpp-oj 适配器（Cookie + Session + 同步判题） |
| `SchoolOJAdapter` | 示例适配器（Token 认证 + 同步判题） |
| `PluginManager` | 插件自动扫描 / 加载 / 实例缓存 |

```python
class BaseOJAdapter(ABC):
    def login(self, username, password) -> LoginResult: ...
    def submit_code(self, problem_id, code, lang="cpp") -> SubmitResult: ...
    def get_judge_result(self, submit_id) -> Optional[JudgeResult]: ...
    def get_problem_list(self) -> list[dict]: ...
    def get_problem_detail(self, problem_id) -> Optional[dict]: ...
    def health_check(self) -> bool: ...
```

**面试可讲**：
> 不同 OJ 系统的 API 差异很大 —— 有的用 Cookie，有的用 Token；有的同步判题，有的异步轮询。我采用适配器模式封装了 BaseOJAdapter 接口，新增 OJ 只需继承该接口实现具体方法，通过 PluginManager 自动注册，不需要改框架代码。这是平台化最关键的一层抽象。

---

### 7. Config Center（配置中心）

**职责**：集中管理所有配置，支持多环境和环境变量覆盖。

```yaml
env: dev
oj:
  base_url: "http://localhost:8080"
  timeout: 30
```

加载优先级：环境文件 > 默认文件 > 环境变量

---

### 8. Task Center（任务调度系统）

**职责**：管理测试任务的生命周期（创建 → 调度 → 执行 → 完成）。

```python
class TaskManager:
    def create_task(self, config) -> Task: ...
    def start_task(self, task_id) -> bool: ...
    def get_task(self, task_id) -> Optional[Task]: ...
    def list_tasks(self, limit=20) -> list[Task]: ...
    def cancel_task(self, task_id) -> bool: ...
```

**当前**：内存队列 + ThreadPoolExecutor，满足单机任务执行需求。
**扩展方案**：后续可替换为 Redis + Celery 分布式任务队列，用于大规模 CI 场景。
**增强计划**：增加 SQLite 持久化，服务重启后任务记录不丢失。

---

### 9. 日志系统（Logging）

**职责**：统一的分级日志体系，支撑问题定位和系统观测。

```python
# utils/logger.py
import logging

def setup_logger(name: str) -> logging.Logger:
    """按模块获取 logger"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    # 文件 handler（按大小轮转）
    file_handler = logging.FileHandler(f"logs/{name}.log")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    ))
    logger.addHandler(file_handler)
    return logger
```

**日志分类**：

| Logger | 用途 | 级别 |
|--------|------|------|
| `oj.executor` | 任务执行过程 | INFO |
| `oj.task_manager` | 任务调度状态 | INFO |
| `oj.api_client` | HTTP 请求详情 | DEBUG |
| `oj.report` | 报告生成记录 | INFO |

**面试可讲**：
> 我通过日志系统追踪一次测试任务的完整生命周期 —— 从任务创建、到每个用例的提交结果、再到最终报告生成。线上定位问题时，直接看 error.log 就能知道哪些任务失败了、原因是什么。

---

### 10. 数据库持久化（SQLite）

**职责**：服务重启后任务记录不丢失，从"内存 demo"升级为"可重启的系统"。

```sql
-- database/schema.sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    name TEXT,
    status TEXT DEFAULT 'PENDING',
    config TEXT,
    result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP
);
```

**说明**：使用 SQLite 而非 MySQL，因为本平台单机部署即可，不需要独立数据库服务。后续如需扩展，SQLite 可平滑迁移到 MySQL/PostgreSQL。

---

### 11. Web Frontend（可视化界面）

**当前**：原生 HTML + CSS + JS（单页内联，零外部依赖）

**功能**：任务配置创建、实时进度展示、历史任务列表、测试报告查看

**目标**：Vue3 + Element Plus（前后端分离，仅做核心页面：任务列表、创建、报告）

---

### 12. Backend - FastAPI 服务层

**职责**：提供 REST API，接收前端请求并调度 Core Engine。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tasks` | 创建并启动测试任务 |
| `GET` | `/api/tasks` | 列出最近任务 |
| `GET` | `/api/tasks/{id}` | 获取任务详情 |
| `POST` | `/api/tasks/generate` | 仅生成用例（不执行） |
| `POST` | `/api/tasks/{id}/cancel` | 取消任务 |
| `GET` | `/api/config` | 获取当前配置 |
| `POST` | `/api/config/reload` | 重新加载配置 |
| `GET` | `/api/reports` | 列出报告 |
| `GET` | `/api/reports/{name}` | 获取报告内容 |
| `GET` | `/api/plugins` | 列出可用插件 |
| `POST` | `/api/plugins/test` | 测试 OJ 连接 |
| `GET` | `/api/health` | 健康检查 |

---

## 五、数据流设计

### 当前执行流程

```
用户点击 Web UI
       │
       ▼
Backend 接收请求 (POST /api/tasks)
       │
       ▼
Task Manager 创建任务 → SQLite 持久化
       │
       ▼
后台线程执行 (ThreadPoolExecutor)
       │
       ├── Case Engine 生成用例
       ├── Executor 执行测试
       ├── Assertion 校验结果
       └── Report Engine 生成报告
       │
       ▼
更新任务状态 → 前端轮询显示
```

### CI 模式执行流

```
python main.py --ci --base-url http://oj:8080 --count 10
       │
       ▼
TaskExecutor.run_task()
       │
       ├── 登录 OJ
       ├── 生成用例
       ├── 执行测试
       ├── 生成报告
       └── 退出码 0（通过）/ 1（失败）
```

---

## 六、非功能性要求

| 要求 | 说明 | 实现方式 |
|------|------|----------|
| 模块解耦 | 各模块通过接口通信，不直接依赖实现 | 接口抽象 / 依赖注入 |
| 可扩展 | 新增 OJ 系统不影响已有代码 | 适配器模式 + 插件注册 |
| 可配置 | 修改行为只需改配置不用改代码 | YAML + 环境变量 + dataclass |
| 可测试 | 平台自身经过充分测试 | pytest + Mock OJ Server |
| 可部署 | 一键部署，环境一致 | Docker + docker-compose |
| 可观测 | 运行状态可追踪 | 分级日志 + 按模块隔离 |
| 可持久化 | 服务重启数据不丢失 | SQLite 任务存储 |

---

## 七、开发路线图

### ✅ 已完成 (Phase 0~2)

| 模块 | 状态 |
|------|:----:|
| 四层架构设计 | ✅ |
| 用例生成器（3 策略） | ✅ |
| API 客户端 | ✅ |
| 执行引擎（顺序 + 并发） | ✅ |
| 结果校验（规则引擎） | ✅ |
| 报告生成（JSON + HTML） | ✅ |
| 插件系统（2 个适配器） | ✅ |
| 配置中心（多环境） | ✅ |
| 任务中心（异步内存） | ✅ |
| Web 页面（单页） | ✅ |
| FastAPI 后端（12 个 API） | ✅ |
| 端到端验证（真实 OJ） | ✅ |

---

### 🔜 Phase 3: 企业级加固（优先级 ⭐⭐⭐⭐⭐）

> 目标：从"能跑的平台"变成"企业可用的平台"

#### 3.1 pytest 测试体系 — 平台自身质量保障

```
tests/
├── conftest.py                   # 共享 fixtures
├── unit/                         # 单元测试
│   ├── test_case_generator.py    # 用例生成器
│   ├── test_executor.py          # 执行引擎
│   └── test_adapter.py           # 适配器
├── integration/                  # 集成测试
│   ├── test_report.py            # 报告模块
│   └── test_api.py               # API 端到端
└── mock/                         # Mock 服务
    ├── mock_oj_server.py         # 模拟 OJ 各种响应
    └── __init__.py
```

**Mock OJ Server**：HTTP 服务，可模拟以下场景：

| 场景 | 说明 |
|------|------|
| 正常判题 | AC / WA / CE / TLE / RE 各状态 |
| 登录异常 | 用户名密码错误 → 401 |
| 提交异常 | 空代码提交 → 400 |
| 超时场景 | 请求不响应 → 超时 |
| 非法 ID | 请求不存在的题目 → 404 |

运行：`pytest tests/ -v`

> **面试价值**：测试平台自身也经过测试，说明你有工程化质量意识。Mock Server 让测试不依赖真实 OJ 环境。

#### 3.2 日志系统

- 按模块分离 logger（`oj.executor`, `oj.task_manager` 等）
- 分级日志：DEBUG / INFO / WARNING / ERROR
- 日志文件按大小轮转
- 通过日志可追踪完整的任务执行链路

> **面试价值**：企业项目要求可观测性。面试时可以说"我通过日志系统追踪一次测试任务的完整生命周期"。

#### 3.3 Docker 部署

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "main.py"]
```

```yaml
version: "3.8"
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs
      - ./reports:/app/reports
      - ./database:/app/database
```

启动：`docker-compose up -d`

> **面试价值**：容器化部署是测试开发基本能力。

#### 3.4 GitHub Actions CI

```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pip install pytest
      - run: pytest tests/ -v --junitxml=report.xml
```

> **面试价值**：提交代码 → 自动测试 → 报告输出，与测试开发日常工作高度相关。

---

### 📋 Phase 4: 能力增强

#### 4.1 SQLite 任务持久化（优先级 ⭐⭐⭐⭐）

- 任务信息写入 SQLite，服务重启后不丢失
- 记录任务 ID、状态、配置、结果、起止时间
- 逐步替代纯内存存储

#### 4.2 Vue3 前端升级（优先级 ⭐⭐⭐⭐）

- 仅做核心页面：任务列表、任务创建、报告查看
- 技术：Vue3 + Vite + Element Plus + Axios
- 目的：证明前后端分离能力

#### 4.3 用户系统（优先级 ⭐⭐）

- 简单的 Token/用户标识
- 用于区分"谁提交了任务"

---

### 📐 Phase 5: 扩展方案（架构设计，按需实现）

#### 5.1 Redis + Celery 分布式任务队列

**触发条件**：当单机 ThreadPoolExecutor 无法满足大规模 CI 并发时。

```
FastAPI → Redis Queue → Celery Worker → Executor
```

**面试话术**：
> 当前版本采用 ThreadPoolExecutor 满足单机任务执行需求，后续如果面对大量 CI 并发任务，可以替换成 Redis + Celery 分布式任务队列。架构上已经做了接口抽象，替换成本较低。

#### 5.2 AI 辅助测试探索（可选特色）

**定位**：辅助生成测试点，不影响核心测试执行链路。

**思路**：
1. 用户输入题目描述
2. LLM 辅助分析生成测试点（正常/异常/边界）
3. 转换为 TestCase 列表进入执行引擎

**注意**：核心测试执行链路不依赖 LLM，AI 部分仅用于辅助测试设计阶段。

**面试话术**：
> AI 部分主要用于辅助测试设计，目前平台的核心测试执行链路不依赖 LLM。调用 LLM 的目的是根据题目描述快速生成测试点，提高测试覆盖率。

---

## 八、项目定位说明

该项目定位为：

> 🎯 **OJ 在线判题系统自动化测试平台**

而不是：

| 错误定位 | 为什么错 |
|----------|----------|
| ❌ 测试脚本 | 脚本无架构、无扩展性 |
| ❌ 自动化 demo | demo 只演示功能，不考虑工程化 |
| ❌ "AI 分布式平台" | 过于夸张，面试容易露馅 |

**核心理念**：平台化而非脚本化。将测试执行能力抽象为服务，通过 Adapter 屏蔽多 OJ 差异，通过策略模式扩展测试用例生成，通过 API 提供服务化接口。

---

## 九、面试指南

### 简历写法

```
OJ 在线判题系统自动化测试平台

项目描述：
基于 Python/FastAPI 设计并实现面向 OJ 系统的自动化测试平台，
支持测试用例生成、接口调用、任务调度、结果校验以及测试报告生成，
用于提升 OJ 系统功能测试和回归测试效率。

技术亮点：
1. 采用策略模式设计测试用例生成模块，支持随机、边界、规则多策略组合；
2. 基于适配器模式抽象不同 OJ 接口差异，新增 OJ 无需修改框架代码；
3. 设计测试执行引擎，支持批量顺序执行和并发执行两种模式；
4. 使用 pytest + Mock OJ Server 构建平台自身测试体系；
5. 基于 Docker + docker-compose 实现容器化部署和持续测试。
```

### 常见面试问答

**Q：为什么自己造测试平台，不直接用 pytest？**

A：pytest 解决的是测试执行问题，而企业中还关心任务管理（谁在什么时候跑了什么测试）、配置管理（不同环境怎么切换）、报告管理（历史记录在哪）、多系统适配（不同 OJ 接口有差异）。所以我将测试执行能力抽象成 Core Engine，通过 FastAPI 提供服务化接口，通过 Adapter 支持插件化扩展。

**Q：你的平台怎么支持新的 OJ 系统？**

A：我定义了 BaseOJAdapter 抽象接口，不同 OJ 的差异（认证方式、API 路径、判题模式）都在适配器层封装。新增 OJ 只需新建一个 adapter.py 继承 BaseOJAdapter，PluginManager 会自动发现注册。目前已经实现了两个适配器：local_oj 和 school_oj。

**Q：你的平台怎么保证自己没问题？**

A：平台本身用 pytest 写了单元测试和集成测试。我还做了一个 Mock OJ Server，可以模拟 AC/WA/CE/TLE/RE 各种判题结果以及登录失败、超时等异常场景，让测试不依赖真实环境就能执行。GitHub Actions 配置了 CI 流程，每次提交代码自动跑测试。

**Q：如果 1000 个测试任务同时进来怎么办？**

A：当前版本采用 ThreadPoolExecutor 并发执行，实测 5 个 worker 能把大批量任务的执行时间压缩到单条最慢用例的时间级别。如果未来面对更大规模的任务量，架构上预留了扩展路径 —— 可以替换为 Redis + Celery 分布式队列，多台机器同时消费任务。

**Q：你们项目用到了什么设计模式？**

A：主要用了两个：适配器模式和策略模式。适配器模式用在插件层，用来屏蔽不同 OJ 系统的接口差异，这是平台化最关键的一层抽象。策略模式用在用例生成模块，不同生成策略可以自由组合。其他模式（工厂、组合、模板方法）是根据模块需求自然引入的。

---

## 附录

### A. 当前项目目录结构

```
OJ-Test-Platform/
├── main.py                        # 启动入口（Web + CI 双模式）
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/test.yml
│
├── backend/
│   ├── app.py
│   └── routers/
│       ├── task_router.py
│       ├── config_router.py
│       ├── report_router.py
│       └── plugin_router.py
│
├── core_engine/
│   ├── case_engine/
│   │   ├── base_generator.py
│   │   ├── random_generator.py
│   │   ├── boundary_generator.py
│   │   ├── rule_generator.py
│   │   └── case_builder.py
│   ├── api_client/
│   │   ├── request_client.py
│   │   └── api_result.py
│   ├── executor/
│   │   ├── base_executor.py
│   │   ├── sequential_executor.py
│   │   ├── concurrent_executor.py
│   │   └── task_executor.py
│   ├── assertion/
│   │   └── judge_oracle.py
│   └── report_engine/
│       └── report_generator.py
│
├── plugins/
│   ├── base_adapter.py
│   ├── plugin_manager.py
│   ├── local_oj/
│   │   └── adapter.py
│   └── school_oj/
│       └── adapter.py
│
├── task_center/
│   ├── models.py
│   └── task_manager.py
│
├── config_center/
│   ├── config.py
│   ├── config.yaml
│   └── config.prod.yaml
│
├── utils/
│   └── logger.py                   # 日志工具
│
├── database/
│   └── schema.sql                  # SQLite 表结构
│
├── frontend/
│   └── index.html
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_case_generator.py
│   │   ├── test_executor.py
│   │   └── test_adapter.py
│   ├── integration/
│   │   ├── test_report.py
│   │   └── test_api.py
│   └── mock/
│       ├── __init__.py
│       └── mock_oj_server.py
│
├── logs/
└── reports/
```

### B. 设计模式使用说明

| 模式 | 使用位置 | 设计目的 |
|------|----------|----------|
| **适配器模式** | `plugins/` | 屏蔽不同 OJ 系统的接口差异，新增 OJ 不改框架代码 |
| **策略模式** | `case_engine/` | 多种用例生成策略可自由组合和扩展 |
| 工厂模式 | `plugin_manager.py` | 按名称动态创建适配器实例 |
| 组合模式 | `case_builder.py` | 组合多策略输出完整用例集 |
| 模板方法 | `executor/base_executor.py` | 固定执行流程框架，子类实现具体执行逻辑 |

> 设计模式是根据模块需求自然引入的，不是为了凑数量。面试时重点说清楚"为什么在这个场景用这个模式"。

### C. 端到端验证结果

- **目标 OJ**：真实部署的 cpp-oj 系统（1.12.75.231:8080）
- **测试结果**：15 个用例全部通过，通过率 100%
- **覆盖状态**：AC / WA / CE / TLE / RE
- **覆盖场景**：正常提交、错误答案、编译错误、运行超时、运行时异常、非法题目 ID

### D. 依赖清单

```txt
fastapi>=0.109.0
uvicorn[standard]>=0.25.0
requests>=2.31.0
PyYAML>=6.0
pydantic>=2.0.0
pytest>=8.0.0          # 开发/测试
```

---

> **文档版本**：v5.1
> **更新日期**：2026-07-06
> **状态**：Phase 3 企业级加固进行中
