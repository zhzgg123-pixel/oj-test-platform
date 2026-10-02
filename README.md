# OJ-Test-Platform

Python / FastAPI OJ 自动化测试平台，正在按已审计的简历能力清单逐步完善。

## 当前状态

当前已导入脱敏源码并建立 pytest + HTTP Mock 测试底座，保留生成器、Adapter、顺序执行、Web/CLI 和基础报告。已修复判定误通过、业务错误解析和自动重复提交；已接通 YAML 题目配置及三类策略，目前 250 条本地回归通过（1 条上游弃用提示）。Web／CLI 已共用 SQLite 持久化任务服务。**完整证据报告、Docker、真实 OJ 联调和 CI 尚未验收完成**。

原始文档 `OJ测试开发工具.md` 是历史资料，其中完成度描述不作为当前能力证明。请以 [进度](docs/progress.md)、[原始审计](docs/initial-audit.md) 和对应测试证据为准。

## 开发环境

主验收 Python 3.12，另计划验证 3.14。Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pytest -q
```

测试默认使用随机本地端口，不访问真实 OJ。JUnit 可通过 `--junitxml=artifacts/tests.xml` 导出。手动启动 Mock：`python -m tests.mock_oj.server --port 8099`；固定测试账户 `tester / test-only` 仅用于该 Mock。Mock 不编译或执行 C++，其测试结果不证明真实判题正确。

E2E 必须显式指定 `--run-e2e --e2e-config <隔离环境配置文件>`；缺文件或未选中任何 E2E 测试时非零退出。真实 E2E 测试将在 S10 添加。

## 开发约定

- 在本仓库开发，原始桌面源码保留；C++ OJ 继续由独立仓库管理。
- 不提交密码、Cookie、令牌、运行数据库或历史报告。已移除导入源码的默认密码。
- 按 [实施计划](docs/implementation-plan.md) 小步修改、测试、提交、推送，核对 Gitee 远端 SHA。
- 设计与验收口径见 [设计约定](docs/design-contract.md)。

## Adapter 兼容约定

新增 `submit_case(case) -> SubmissionReceipt` / `get_result(id)` 接口；旧 `submit_code` 和 `get_judge_result` 保留供现有插件迁移。LocalOJ 是同步协议，必须读取本次回执，不支持凭任意 ID 读取最近结果。`AuthResult` 兼容旧 `LoginResult` 名称。Web/CLI 使用独立 ExecutionCredentials 传递登录信息，不再把密码装入 TaskConfig。旧 `expected_status="ERROR"` 不再有效，需使用明确 HTTP 或业务错误预期；生成器的全面配置迁移在 S04 完成。

## Web 与 CLI

```powershell
.\.venv\Scripts\python.exe main.py --config config_center/config.yaml
.\.venv\Scripts\python.exe main.py --ci --config config_center/config.yaml --strategies random --count 1
```

CLI 密码通过 `OJ_PASSWORD` 传入，用户名通过 `OJ_USERNAME` 或 `--username` 传入；不再接受 `--password`。不要把真实凭据提交到仓库。

任务参数优先级为显式 CLI 参数 > `OJ_*` 环境变量 > 指定 YAML > 默认值。支持 `--problem-id`（兼容 `--problem`）、`--case-count`（兼容 `--count`）、`--seed`、`--timeout`、`--poll-timeout` 、`--db` 和 `--report-dir`。通过 `--mode concurrent --max-workers 3` 选择线程池并发（1–16 worker）；API 使用同名字段。

CLI 退出码：0 表示至少执行一条且全部通过、报告生成成功；1 表示运行或用例失败；2 表示参数／配置错误或同库执行锁冲突；130 表示 Ctrl+C。`--output` 和报告只保存非秘密任务配置。

API 的任务创建成功返回 202，非法配置返回 422。配置重载使用启动时同一个文件；重载失败保留原配置，报告目录或数据库路径变更需重启。导入 `main` 或 `backend.app` 不创建运行目录。

## YAML 题目与可复现生成

内置 `a_plus_b` 和 `max_of_two`，使用 `--profile max_of_two --problem-id 2` 选择本地配置及远端题号。远端题号需要对应相同题意，真实 OJ 联调仍待 S10 验证。

`--case-count` 是任务总用例数，按所选 random／boundary／rule 策略均分并交错执行；相同配置与 seed 生成相同提交源码。随机策略抽样程序模板，边界策略覆盖 CE／TLE／RE 模板，规则策略覆盖匿名、缺失题目和空源码。具体语义见 [profiles](profiles/README.md)。匿名用例使用独立无登录会话。

`GET /api/v1/profiles` 列出可用题目；生成接口返回实际源码、源码哈希、profile 哈希和 seed。快照已持久化，完整证据报告仍待 S07。

## 持久化任务与历史

Web／CLI 共用 TaskService，先原子保存配置、题目快照和实际源码，再进入单消费者队列；最多等待 20 个任务，满队列返回 429。结果逐条保存，凭据仅在内存中保留到任务终态。SQLite 使用外键、WAL、短事务和版本迁移；版本 2 新增任务名称并保留版本 1 历史。已有数据升级前应停止服务并备份数据库。

数据库优先级：`--db` > `OJ_DB` > YAML `test.db_path` > `runtime/tasks.db`；报告目录同理使用 `--report-dir`／`OJ_REPORT_DIR`／`test.report_dir`。相对路径相对于启动工作目录。Web 正占用某个数据库时，同库 CLI 退出 2；可指定 `--db runtime/ci.db` 独立执行。更换报告根目录后需同时迁移相应报告文件。

启动时只有获得操作系统运行锁的进程会恢复遗留活动任务：状态改为 INTERRUPTED，已完成结果保留，未完成用例为 ERROR／PROCESS_INTERRUPTED；不会自动重放提交。Windows 已有真实子进程验证，POSIX 分支待 Docker／CI 验证。顺序和并发取消保留在途结果、停止后续提交；关闭超时保留运行锁。COMPLETED 表示执行结束，只有所有用例通过且两种报告可读、哈希匹配才有 `success=true`。

| 接口 | 用途 |
|---|---|
| `POST /api/v1/tasks` | 保存并排队，202；参数与原 `/api/tasks` 一致 |
| `GET /api/v1/tasks?limit=20&offset=0` | 持久化历史，limit 1–100 |
| `GET /api/v1/tasks/{id}` | 任务配置、状态、统计和成功判定 |
| `GET /api/v1/tasks/{id}/cases` | 实际源码、预期、哈希和逐条结果 |
| `GET /api/v1/tasks/{id}/reports/{html或json}` | 按数据库关联安全读取报告 |
| `POST /api/v1/tasks/{id}/cancel` | 接受活动任务取消；终态 409，不存在 404 |
| `DELETE /api/v1/tasks/{id}` | 仅删除终态任务及其报告；活动任务 409 |

旧 `/api/tasks` 委托同一服务，保留旧页面需要的时间字符串和返回字段。报告别名 `/reports/{任务UUID}.json`／`.html` 及已有平铺报告仍可读取。CLI 的 `--output` 返回 task_id，该任务之后可通过 Web 查询。

## 有界并发

并发调度最多保留 max_workers 个在途 future，完成后才补充新用例。每个执行用例创建并关闭自己的 Adapter／Session，认证用例独立登录，匿名用例不带 Cookie；因此登录请求数会随认证用例数增加。旧 create_instance 工厂也不再缓存实例，调用者负责 close。

顺序和并发复用同一单用例判定逻辑及逐条持久化回调。结果按输入顺序输出；任一 worker 登录／准备失败会停止补位并明确失败，持久化失败不自动重提代码。HTTP Mock 已验证请求重叠、future 数量上限、乱序结果归属及会话隔离；取消屏障测试已验证停止补位、在途结果保留、CLI KeyboardInterrupt 退出130及关闭超时保留锁。运行中取消会记录远端可能仍在执行；排队取消标记为没有远端执行。报告发布与终态转换串行化，发布完成后取消返回409。CLI 测试通过 Python interrupt_main 触发，不等同于 Windows 控制台信号验收。

## 报告证据（S07 进行中）

报告 schema_version=2 已保留逐例实际源码、题号、seed、源码/profile 哈希、结构化预期与实际观察、错误和尝试次数。任务报告包含 SQLite 保存的题目快照与平台/被测版本；sut_sha 未知时保留 null，不假造版本。HTML 对动态用例及配置文本转义，报告 ID 使用 UUID 防止同秒覆盖。无结构化预期的旧错误用例保留原始 expected 和诊断，不因报告阶段重新校验而丢失报告。双格式先完成渲染，暂存文件 flush/fsync 后逐个原子替换，报告元数据成对事务提交；普通写入/登记失败回滚并清理本次文件。文件系统与 SQLite 不是同一事务，强制终止可能留下未登记孤立文件，不宣称断电原子性。LocalOJ 和报告共用敏感字段与已知秘密替换函数；报告配置采用字段白名单，先从原始响应识别凭据再过滤响应字段。源码被脱敏时标记 source_redacted，保留原始源码哈希；规范哈希、报告标识及判题枚举不会因短密码巧合而改变。错误分布从脱敏结果重建。完整快照接口与下载验收仍在 S07 后续完成。
