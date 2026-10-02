> 规划快照（2026-10-02）。用户现已授权执行及分步推送；文中的“本轮不修改”描述的是规划阶段。当前进度以 progress.md 为准。

# OJ 自动化测试平台：简历对照与补齐建议

核对日期：2026-10-02。范围：用户提供的 PDF 简历及桌面目录中的源码。此次只分析，不修改项目，不连接真实 OJ 或数据库，不执行远程 CI、部署、提交或推送。

## 1. 结论与版本边界

**这份源码已经具备用例生成、适配器、顺序执行、Web/API、命令行和基础报告，但还不能完整支撑简历描述。最明显的缺口是 YAML 题目配置、SQLite 历史持久化、公开入口的并发执行、平台自身的 pytest/Mock Server、Docker 和 GitHub Actions。报告的失败输入留存及判定正确性也需要补齐。**

当前平台不是需要全部重写。已有模块划分可以保留，工作重点是打通能力、修正误判、补齐证据。

本次源码根目录：`C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/`。

| 目录 | 本次核对结果 |
| --- | --- |
| `OJ-Test-Platform` | Python/FastAPI 测试平台。该目录及父目录未识别为 Git 仓库，无法给出平台的提交 SHA。 |
| `cpp-oj` | C++ 被测 OJ。HEAD 为 `84ded72d705cd9e950ad5d4d644e1cefdb4775d5`，检查时 Git 工作区状态输出为空。 |
| 平台 `tests` | 空目录；实际运行 pytest 收集，输出 `no tests collected`。 |
| 平台 `tp_b64_00` 至 `tp_b64_02` | 内存解码为归档并检查目录条目，未执行或释放归档；未发现能补上上述测试、容器、工作流缺口的对应文件。 |

历史记录曾提到其他路径中的更完整版本；它仅提示“可能存在版本分叉”，不能作为本目录已实现功能的证据。本次未查证其他目录或远程仓库的最新状态。正式改动前，先确定这份桌面源码是否为后续开发基线，避免重做别处已经完成的功能。

## 2. 简历逐项对照

对照来自所提供 PDF 第 1 页“2026.04–2026.07 OJ 自动化测试平台”。“有实现”指源码或隔离检查支持该能力，不代表真实 OJ 联调已经通过。

| 简历表述 | 当前证据 | 结论 | 补齐标准 |
| --- | --- | --- | --- |
| Python、FastAPI | 存在应用工厂、路由、任务接口；本地 TestClient 健康接口 200 | 已有基础实现 | 与真实 OJ 完成受控端到端运行 |
| YAML 配置题目规则 | YAML 只用于 OJ 地址、超时、报告目录等全局配置；CaseBuilder 不加载题目文件 | **未实现该项** | 按题目加载、校验 YAML；未知题目明确报错；题目模板和预期来自配置 |
| 随机、边界、规则三类策略 | 三个生成器均存在；随机挑固定代码模板，边界是代码/题号异常，规则写在 Python 中 | 部分符合 | 以题目配置驱动策略，记录种子和实际生成内容，证明新增题目不改执行器 |
| Adapter 封装登录、提交、结果查询 | BaseOJAdapter、LocalOJAdapter、PluginManager 完整存在，能发现两个适配器 | 已有基础实现 | 补响应契约、业务错误解析、会话隔离及自动化测试；school_oj 目前只可认定为示例实现 |
| 新增题目复用执行流程 | 题目 ID 可以传递，但 A+B 模板和预期不变 | 部分符合 | 至少以两道逻辑不同的题验证新增 YAML 即可运行 |
| Web 与命令行入口 | 前端、FastAPI、`main.py --ci` 均存在 | 已实现入口 | 两种入口使用同一配置及执行链，非法配置和零用例不能成功退出 |
| 顺序及线程池并发执行 | 两种执行器均存在；独立组件检查均能汇总五种模拟状态；TaskExecutor 固定创建 SequentialExecutor | **并发未接入任务入口** | Web/API/CLI 可设置模式与 worker 数，配置传到执行器；验证请求确实重叠且会话不串扰 |
| SQLite 保存任务配置、测试输入和执行结果 | TaskManager 使用内存字典；无对应存储层、SQLite schema 或读写调用 | **未实现** | 任务、生成输入、结果均落库；新进程恢复历史；异常中断状态可识别 |
| 历史任务追溯 | 内存任务列表及磁盘报告列表存在，重建 TaskManager 后任务消失 | 部分符合 | 可通过 task_id 查询配置、具体输入、结果和报告，且重启后仍有效 |
| AC/WA/CE/TLE/RE 状态校验 | 实际执行器比较预期和实际状态；独立 JudgeOracle 未被执行链调用 | 基础具备，正确性有缺陷 | 修正负向断言；统一采用可信的状态及响应契约，不直接接上当前 Oracle |
| HTML、JSON 报告 | 两种报告生成器及历史文件存在 | 已有基础实现 | 修正报告 ID 冲突，保证任务关联和报告不覆盖 |
| 报告包含失败输入及预期/实际差异 | 有状态差异；没有提交源码、stdin、题目快照、随机种子等完整失败输入；HTML 不显示 error_message | **部分符合** | 报告能直接展示复现输入、预期、实际、错误原因和执行环境标识 |
| pytest 与 Mock Server 验证平台接口逻辑 | 平台测试目录为空，无 Mock Server；C++ OJ 的 Python 测试属于另一个测试对象 | **平台这一项缺失** | 提供针对平台的单元及 HTTP 契约测试，无真实 OJ 也能运行 |
| Docker | 未发现本项目可用的 Dockerfile/Compose 文件，文档中有规划或示例 | **交付文件缺失** | 从新环境构建、启动、挂载数据卷、重启并查询历史 |
| GitHub Actions 执行回归和归档 | 未发现实际 `.github/workflows` 工作流 | **交付文件与运行证据缺失** | 真实仓库工作流执行成功，失败门禁有效，并能下载报告制品 |

技术栈里的 MySQL 与 SQLite 不能互相替代：C++ OJ 使用 MySQL，并不表示 Python 测试平台已使用 SQLite 管理任务。

## 3. 应优先修复的正确性问题

### 3.1 负向用例可能无条件通过

位置：`OJ-Test-Platform/core_engine/executor/sequential_executor.py:92`、`:108`、`:123`、`:129`。

只要 `expected_status == "ERROR"`，提交失败、轮询无结果、Python 异常，甚至收到正常 `AC` 结果，都可能标为 `PASSED`。

本次隔离复现：

| 场景 | 当前结果 | 合理验收要求 |
| --- | --- | --- |
| 非法题目用例期望错误，实际返回 AC | PASSED，actual=AC | FAILED：实际行为违反预期 |
| 期望题目错误，实际 HTTP 401 | PASSED，错误文本丢失 | 不得因任意 HTTP 错误通过；应核对具体状态及业务错误 |
| 期望题目错误，网络连接失败 | PASSED | ERROR 或 BLOCKED，不能充当业务预期达成 |

需要区分 HTTP 错误、业务拒绝、判题状态、平台执行异常。负向测试应该断言明确的错误，而不是泛化成“发生任何事情都通过”。

### 3.2 零用例可以让 CI 假通过

位置：`core_engine/case_engine/case_builder.py:42`，`main.py:117`，`backend/routers/task_router.py`。

空策略生成零条用例，未知策略只打印信息后跳过；CLI 仅检查 failed/error 是否大于零。

本次模拟“空策略 + 登录失败”，实际结果为 total=0、failed=0、error=0、退出码 0，并输出“CI 检查通过”。本地 API 也接受空策略并返回 200、total=0。

验收：空策略、未知策略、非正数量、没有可执行用例、登录失败都必须有明确失败结果；CLI 返回非零。不得以零条测试为回归成功证据。

### 3.3 当前并发类不能直接接入就视为完成

位置：`core_engine/executor/task_executor.py:67`，`plugins/plugin_manager.py:65`，`plugins/local_oj/adapter.py:25`，`core_engine/executor/concurrent_executor.py:94`。

已确认的事实：TaskExecutor 固定走顺序执行；PluginManager 以适配器名和 URL 缓存对象；相同目标的任务会复用同一个带 Cookie 和最近一次判题结果的对象；ConcurrentExecutor 将同一 adapter 传给所有 worker。

风险：不同任务使用不同账号时，登录态可能互相覆盖；同步适配器的共享最近结果也需要验证是否发生串扰。本次只证明对象确实共享，未在真实 OJ 上复现账号或判题结果串扰。

验收：定义每任务、每 worker 的会话归属；并发测试包含不同账号和不同判题结果；验证每条结果只能关联自己的输入。独立组件的线程池成功不代表公开入口和真实 OJ 已完成并发验收。

### 3.4 任务取消仅改变显示状态

位置：`task_center/task_manager.py:102`、`:147`。

取消方法不通知执行器停止；后台完成后无条件写回 COMPLETED。本次通过阻塞的模拟执行器复现：RUNNING → CANCELLED → COMPLETED。

验收：取消信号能阻止后续用例提交；明确已经发出的请求如何处理；取消状态不被完成逻辑覆盖；留下已完成和未执行用例的统计。

### 3.5 适配器把 HTTP 200 业务错误当提交成功

位置：`plugins/local_oj/adapter.py:70`、`:90`，`cpp-oj/src/main.cpp:206`。

真实 OJ 源码在题目不存在时返回含 `success=false` 和错误原因的 JSON；该分支未显式改变默认 HTTP 状态。适配器只检查 HTTP 200，然后将没有判题结果的响应标为提交成功。执行器可能继续轮询缓存，最终显示判题超时，丢掉“题目不存在”的直接原因。

本次模拟该响应，确认 `submit_success=true`、`judge_result=None`。

验收：响应解析同时判断 HTTP 层、业务成功字段和必需的判题字段；业务拒绝立即返回准确分类及原因；同步接口缺失结果不冒充异步处理中。

### 3.6 JudgeOracle 文件存在，但既没接入，也不能原样接入

位置：`core_engine/assertion/judge_oracle.py:49`，`core_engine/executor/sequential_executor.py:126`。

当前实际执行链做状态字符串比较，未调用 JudgeOracle。这不意味着完全没有判题校验，但不能将独立 Oracle 的存在作为已启用复杂规则引擎的证明。

本次直接检查 Oracle：预期 WA、实际 CE 且 passed=0/total=2 时判通过；预期 RE、实际 RE 时因统一 JudgeResult 没有 exit_code 而判失败。TLE/MLE 阈值还硬编码为 1000ms/65536KB。

验收：先设计统一结果契约，再选择整理现有 Oracle 或以清晰的状态断言实现；若核对时间/内存，应使用题目限制，并考虑服务端返回字段语义。

### 3.7 报告还不能支撑完整复现

位置：`core_engine/report_engine/report_generator.py:45`、`:84`、`:104`、`:120`，`main.py:84`、`:93`。

- 报告只保存状态、描述等摘要，没有提交代码或完整输入快照。即使程序内 TestCase.metadata 有种子/输入，报告也丢掉它。
- HTML 不展示 JSON failed_cases 中的错误文本。
- 文件名只有秒级时间戳。同一秒生成两份报告会写入同一路径；本次固定时钟模拟已确认后一份覆盖前一份。
- CLI 将含密码的 config 原样交给报告和输出 JSON；用虚构字符串检查确认密码会进入报告。Web 的 TaskConfig.to_dict 则已省略密码，两条入口行为不一致。

验收：用 task_id/run_id 或唯一 ID 关联报告；保存完整用例和脱敏配置；HTML 与 JSON 都呈现失败原因；同秒多个任务的报告不覆盖；报告制品不含密码或 Cookie。

## 4. 用例生成到底还差什么

当前随机策略是“从 AC/CE/WA/TLE 代码池选模板”，不是根据任意题目的输入范围生成随机数据。默认 seed 固定为 42；底层虽能读取 seed，但公开任务配置没有传入它，metadata 又写死为 42。

当前边界策略是短代码、无输出、非法题号等固定场景；并没有针对不同题目的数值范围、数组规模、空输入等题目边界配置。

规则策略写死 A+B 代码。此次将 problem_id 从 1 改成另一题，生成的代码和预期完全相同，仅目标题号变化。对于不做加法的新题，这些 AC/WA 标签不再可靠。

还有两个用例含义偏差：

- `AUTH-UNATH-SUBMIT` 名为未登录提交，但执行器在批量执行前统一登录；C++ 提交接口实际调用 check_auth。它不能证明未登录权限测试已完成。
- `PARAM-INVALID-LANG` 提交 Python 文本，但统一 TestCase 默认 lang 仍是 cpp；现有 C++ 提交流程未按 lang 切换编译器。当前更像“把非法 C++ 源码编译成 CE”，不能证明语言参数校验。

最小补齐方案：题目 YAML 定义题目标识、代码模板/基准解、预期状态、生成参数、策略和必要的资源限制；CaseBuilder 读取题目配置，新增题目不改执行器。将题目判题测试与鉴权、参数校验等接口用例分开建模。

还应明确“测试输入”的含义：

1. 若指提交给 OJ 的源码、语言、题号等请求输入，当前接口可以支持，但必须保存实际提交内容。
2. 若指程序 stdin 及期望 stdout，当前适配器只提交代码，实际测试数据由 OJ 数据库决定。要实现随机数值输入，需要在受控 OJ 中准备测试数据或增加明确的运行接口，并保存 fixture 对应关系，不能只在平台生成数据却不传给被测系统。

这两种能力应在 README、演示和面试表述中保持一致。

## 5. 平台测试和 OJ 测试要分清

`cpp-oj/tests/python/` 确实存在 pytest 用例，涵盖注册、登录、管理员操作和判题。这些文件会访问 localhost:8080，并读取 MySQL 配置、创建题目。它们是被测 OJ 的真实接口测试，不能替代 Python 测试平台自身的测试和 Mock Server。

此次没有执行这些测试，原因是尚未确认本机 OJ 和数据库的具体目标、初始化状态及清理方案。也未执行 C++ 构建；代码包含 fork、unistd、mkdtemp 等 Linux/POSIX 依赖，本次没有准备对应编译运行环境。

建议形成三个测试层次：

| 层次 | 验证内容 | 通过条件 |
| --- | --- | --- |
| 平台单元测试 | YAML 校验、生成确定性、状态断言、错误分类、报告数据、持久化、取消 | 不依赖真实 OJ；每项关键错误都有回归 |
| 平台与 Mock HTTP 服务 | 登录 Cookie、状态映射、业务失败、401/403/404/5xx、超时、非法 JSON、同步/异步结果 | 覆盖真实 HTTP 请求和响应解析，能注入异常 |
| 平台与真实 C++ OJ | 已知题目、五类判题状态、串行/并发、真实报告及历史查询 | 受控环境、可识别 fixture、执行证据与清理记录齐全 |

本次临时 Mock/隔离检查只是审计证据，不等于项目已经具备简历中的测试体系。

## 6. 按依赖排序的改造建议

| 顺序 | 工作包 | 最低验收标准 |
| --- | --- | --- |
| 0 | 固定项目基线 | 确认是否存在更新副本；平台进入明确版本管理；记录源代码版本 |
| 1 | 修判定、空任务和响应解析 | 错误 AC、错误 HTTP、网络失败不假通过；零用例 CLI 非零；业务错误直接说明原因；先补回归 |
| 2 | 建立题目配置和用例快照 | 两道逻辑不同的题仅增加 YAML 即可使用；相同配置+seed 可复现；未知题目失败 |
| 3 | SQLite 持久化 | 任务配置、用例快照、结果和报告关联落库；新进程查询完整；运行中重启有明确恢复/中断状态 |
| 4 | 接通并发与任务生命周期 | Web/API/CLI 可选模式；有界并发；账号/结果隔离；取消有效；统计一致 |
| 5 | 完善报告 | JSON、HTML 均展示失败输入、差异、原因；唯一报告 ID；无明文凭据 |
| 6 | 完善 pytest 与 Mock Server | 平台独立回归可运行；异常路径和上述误判有覆盖；保存 JUnit/测试结果 |
| 7 | Docker 与 GitHub Actions | 干净环境可启动；SQLite/报告卷持久；CI 真正执行测试；成功及失败时均按规则归档；留下运行链接 |
| 8 | 真实 OJ 验收、同步材料 | 受控端到端测试通过；README、演示、简历都与实际能力一致 |

SQLite 建议最小保存：任务 ID、创建/起止时间、状态、执行配置快照、目标环境标识、题目配置版本、随机 seed；每条用例的题号、源码、语言、预期断言、生成来源；每条执行结果的实际状态、HTTP/业务信息、耗时、错误分类、报告 ID。无需保存登录密码；重跑时重新提供凭据。

这里的“历史追溯”不仅是保存报告文件。它要求能够回答：哪一版平台在什么目标环境，用哪份题目配置和具体输入运行，得到什么结果。重跑也不能悄悄用修改后的模板重新生成另一批用例。

## 7. 一套能覆盖简历的演示验收

1. 在明确的代码版本上启动平台和受控 C++ OJ，显示环境、题目 fixture 和配置版本。
2. 导入两道逻辑不同的题目 YAML，展示三种策略生成的具体用例与预期。
3. 从 Web 顺序运行，包含 AC/WA/CE/TLE/RE 的已知解或错误解；检查期望与实际一致。
4. 从命令行运行同一批固定用例，验证退出码和报告。
5. 切换线程池并发，用时间线/受控延迟证明存在重叠执行，核对每条输入和结果对应。
6. 注入一个状态不匹配和一个连接错误，前者应为失败，后者应为执行错误，报告展示不同原因。
7. 查看失败源码/请求输入、预期、实际和原始错误；同秒两个任务报告互不覆盖。
8. 重启平台，仍可查询之前任务、输入、结果及报告；正在运行时中断的任务不能永久假装 RUNNING。
9. 运行 pytest + Mock HTTP 服务回归；故意引入错误时测试确实失败。
10. 在真实 GitHub Actions 运行中验证测试执行和报告下载；Docker 重启后历史仍保留。

完成这些验收后，简历三条主要描述才有对应的实现、演示和验证证据。

## 8. 本次验证结果与限制

| 检查 | 状态 | 证据边界 |
| --- | --- | --- |
| 简历 PDF 文字与整页视觉核对 | PASS | 只核对 OJ 项目对应表述，不评价其他经历真实性 |
| 目录及源码调用链核对 | PASS | 包含平台、与平台相关的 C++ 路由/测试、现有报告、归档目录条目 |
| FastAPI 本地健康接口 | PASS | TestClient 200，不能证明 OJ 服务健康或真实登录成功 |
| 两种执行器模拟五类状态 | PASS | 每种均 5/5；并发使用五方 barrier 证明实际重叠；无真实判题 |
| 负向断言、零用例门禁、取消、持久化、报告唯一性 | FAIL | 以本次隔离复现为证，不是只凭文档推断 |
| 平台已有 pytest 测试收集 | FAIL | `no tests collected`；不能报成测试全部通过 |
| 项目文件未改变 | PASS | 核心探针前后 495 个非 `.git` 文件内容哈希一致；探针、报告只写当前聊天工作目录 |
| 真实 OJ/数据库联调与 C++ 编译 | NOT_RUN | 未准备和确认受控环境；未执行会写入数据库的测试 |
| Docker 构建/启动、GitHub Actions 实跑 | NOT_RUN | 当前目录缺对应交付文件；未访问远程运行记录 |

现有磁盘报告摘要：

| 历史文件 | 总计 | 通过 | 失败 | 错误 |
| --- | ---: | ---: | ---: | ---: |
| `report_20260707_014637.json` | 20 | 6 | 5 | 9 |
| `report_20260707_015638.json` | 18 | 12 | 0 | 6 |

这些是已有文件内容，不是本次执行结果，且部分用例与当前生成器不同。缺少可靠的代码版本和环境关联，不能证明当前版本已经通过真实回归，更不能将“普通失败为 0”解读为全通过。

## 9. 源码定位索引

以下位置均属于本次用户提供的源码；完整路径可以在本机打开。

| 主题 | 位置 |
| --- | --- |
| 题目策略组合 | [CaseBuilder](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/core_engine/case_engine/case_builder.py:28) |
| 固定代码模板 | [RandomGenerator](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/core_engine/case_engine/random_generator.py:13) |
| 固定规则与鉴权用例 | [RuleGenerator](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/core_engine/case_engine/rule_generator.py:20) |
| 全局 YAML 配置 | [AppConfig](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/config_center/config.py:52) |
| 固定顺序执行 | [TaskExecutor](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/core_engine/executor/task_executor.py:67) |
| 负向误判 | [SequentialExecutor](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/core_engine/executor/sequential_executor.py:123) |
| 并发组件 | [ConcurrentExecutor](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/core_engine/executor/concurrent_executor.py:92) |
| 适配器缓存 | [PluginManager](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/plugins/plugin_manager.py:65) |
| 提交结果解析 | [LocalOJAdapter](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/plugins/local_oj/adapter.py:56) |
| 内存存储 | [TaskManager](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/task_center/task_manager.py:31) |
| 取消实现 | [cancel_task](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/task_center/task_manager.py:102) |
| 独立 Oracle | [JudgeOracle](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/core_engine/assertion/judge_oracle.py:49) |
| 报告结构 | [ReportGenerator](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/core_engine/report_engine/report_generator.py:70) |
| CLI 通过条件 | [main.py](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/main.py:117) |
| 前端错误计数字段 | [frontend/index.html](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/frontend/index.html:979) |
| C++ 实际提交鉴权和响应 | [cpp-oj/src/main.cpp](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/cpp-oj/src/main.cpp:185) |
| 真实 OJ pytest fixture | [test_judge.py](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/cpp-oj/tests/python/test_judge.py:55) |
| 文档中的未完成列表 | [OJ测试开发工具.md](C:/Users/zhuohongze/Desktop/cpp-oj-vibecoding/OJ-Test-Platform/OJ测试开发工具.md:54) |

文档本身存在口径冲突：开头将 SQLite 写为待实现、测试/容器/CI 写为进行中，后面的架构说明和面试回答又写成已经完成。应在实现及验收后同步文档；文档中的目录树、代码片段和面试话术不能替代实际交付文件。

此外，前端读取 `t.result.errors`，后端实际返回 `error`；`--config` 虽然传入 create_app，但 create_app 内未使用 config_path。它们不是简历的主要缺口，却会影响演示，应一并列入后续修复。
