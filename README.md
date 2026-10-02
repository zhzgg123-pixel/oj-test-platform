# OJ-Test-Platform

Python / FastAPI OJ 自动化测试平台，正在按已审计的简历能力清单逐步完善。

## 当前状态

当前已导入脱敏源码并建立 pytest + HTTP Mock 测试底座，保留生成器、Adapter、顺序执行、Web/CLI 和基础报告。已修复判定误通过、业务错误解析和自动重复提交；已接通 YAML 题目配置及三类策略，目前 191 条本地回归通过（1 条上游弃用提示）。**SQLite、完整并发入口、Docker、CI 尚未验收完成**。

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

任务参数优先级为显式 CLI 参数 > `OJ_*` 环境变量 > 指定 YAML > 默认值。支持 `--problem-id`（兼容 `--problem`）、`--case-count`（兼容 `--count`）、`--seed`、`--timeout`、`--poll-timeout` 和 `--report-dir`。并发模式在 S06 接通前明确拒绝，不会静默变成顺序。

CLI 退出码：0 表示至少执行一条且全部通过、报告生成成功；1 表示运行或用例失败；2 表示参数／配置错误；130 表示 Ctrl+C。`--output` 和报告只保存非秘密任务配置。

API 的任务创建成功返回 202，非法配置返回 422。配置重载使用启动时同一个文件；重载失败保留原配置，报告目录变更需重启。导入 `main` 或 `backend.app` 不创建运行目录。

## YAML 题目与可复现生成

内置 `a_plus_b` 和 `max_of_two`，使用 `--profile max_of_two --problem-id 2` 选择本地配置及远端题号。远端题号需要对应相同题意，真实 OJ 联调仍待 S10 验证。

`--case-count` 是任务总用例数，按所选 random／boundary／rule 策略均分并交错执行；相同配置与 seed 生成相同提交源码。随机策略抽样程序模板，边界策略覆盖 CE／TLE／RE 模板，规则策略覆盖匿名、缺失题目和空源码。具体语义见 [profiles](profiles/README.md)。匿名用例使用独立无登录会话。

`GET /api/v1/profiles` 列出可用题目；生成接口返回实际源码、源码哈希、profile 哈希和 seed。快照的持久化与完整报告分别在 S05／S07 接入。

## 存储层进度

SQLite repository 已加入，保存任务配置、题目快照、实际提交源码、逐条结果和报告元数据。输入原子写入，结果幂等保存，使用外键、WAL 与短事务；不接收登录凭据。相同逻辑用例在不同任务中使用不同 UUID。

当前 Web／CLI 尚未切换到持久化任务服务。运行锁及恢复已通过 Windows 子进程测试，任务服务和历史接口仍属于 S05b 后续接线，不能据此认定现有 Web 任务已支持重启恢复。repository 的恢复方法仅供取得运行锁后的服务调用。
