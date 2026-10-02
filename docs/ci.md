# 持续集成与证据验收

GitHub 仓库：<https://github.com/zhzgg123-pixel/oj-test-platform>。
Gitee 保留为主远端 `origin`，GitHub 为第二远端 `github`。

## 本地验证证据门禁

在项目根目录、安装测试依赖后执行（PowerShell）：

```powershell
$revision = git rev-parse HEAD
python -m pytest -m "not e2e" --junitxml=artifacts/junit.xml
python -m scripts.ci_demo --output-dir artifacts/demo --platform-sha $revision
python -m scripts.check_evidence --junit artifacts/junit.xml --demo artifacts/demo/manifest.json --expected-sha $revision --output artifacts/evidence.json
```

每条命令都必须检查退出码；报告生成成功不能抵消 pytest 失败。
演示输出目录和验收输出文件必须是新路径，重复运行请使用新的路径，避免把旧证据当作本次结果。
SHA 标识已提交源代码；工作区有改动时，只能视为该基线上的本地开发验证。

演示使用 TaskService 创建六条用例，通过本机 HTTP Mock 执行并由正式报告生成器输出 HTML、JSON。
清单记录任务 ID、源代码 SHA、结果数量和文件 SHA-256；临时数据库与服务在执行结束后关闭清理。
这证明平台执行与报告链路，不代表 C++ 判题验收或压力容量。

证据门禁拒绝零用例、全跳过、失败/错误、JUnit 数量不一致、报告缺失或为空、摘要不一致、
报告哈希变化、版本不一致以及清单中的越界路径。失败退出 1，成功才写入验收 JSON。

## 当前交付边界

S11a 提供本地报告生成与证据门禁。S11b 工作流包含 Python 3.12/3.14 回归矩阵与独立 Docker smoke，
在 push、pull_request 或手动触发时运行，仅授予 contents:read 权限。pip 缓存键包含测试依赖锁哈希。
官方 Action 的版本在实施时经 GitHub API 核验，使用完整提交 SHA 固定；升级需重新核验。

pytest、演示报告生成和证据门禁分别运行，失败不会被后续步骤覆盖；即使测试失败仍尝试生成并归档报告。
Docker job 验证真实 HTTP 任务，再重建容器并核对同一任务和报告哈希，归档实际 HTML/JSON 与服务日志。

真实 C++ E2E 已完成远端运行及下载制品核验，结果与范围见下方验收记录。

## 首轮远端验收

[运行 37032626190](https://github.com/zhzgg123-pixel/oj-test-platform/actions/runs/37032626190)
对应提交 `4fb18d31f30a51dbcf72b4722009a7e1ecdf25e6`，与 Gitee 阶段分支读回一致。
Linux Python 3.12.14、3.14.7 各 304 条回归通过，Docker smoke 六条用例与容器重建持久化通过。
下载的两个矩阵制品再次通过证据门禁，Docker HTML/JSON 与 smoke 清单哈希一致。
本地保留在 `artifacts/ci-37032626190/`，摘要在 `docs/evidence/index.json`。

## 失败后保留制品

独立分支 `verify/ci-failure-evidence` 的 `ab584a3f85b11f070758577231cbe83fea9eefae`
仅新增一条确定失败的测试，不合入 main。
[运行 37032980025](https://github.com/zhzgg123-pixel/oj-test-platform/actions/runs/37032980025)
在两个 Python 版本均产生 305 条用例、1 条预期失败；pytest 和证据门禁步骤均失败，
演示报告生成和制品上传均成功。下载后核实唯一失败就是验证用例，HTML/JSON 非空且哈希吻合，
未生成虚假的成功 evidence.json。Docker 独立作业仍通过。

## 真实 C++ CI

`real-cpp-e2e` 在独立 GitHub Ubuntu runner 内检出固定的公开 Gitee SUT 提交，生成专用随机凭据，
构建真实 g++ 判题器、MySQL 和仅绑定回环的入口，再校验部署身份并执行 `tests/e2e` 的 32 条用例。
固定源码和本地复现命令见 [真实 OJ 文档](e2e.md)。当前 SUT 已核实可匿名读取，因此不需要 CI secret；
若以后改为私有仓库，缺少凭据应明确失败，不能跳过后宣称 E2E 通过。

服务日志、JUnit、测试清单及 HTML/JSON 通过 `scripts.ci_e2e_artifacts` 复制到独立上传目录。
收集器替换本次生成的密码，仅允许文本证据扩展名，不复制 SQLite 数据库、私有设置或派生 SQL。
原始本地证据保持不变；报告本身已有脱敏逻辑。测试失败仍执行收集与上传，失败状态不会被归档步骤抵消。

正常 main 在 [运行 37033319446](https://github.com/zhzgg123-pixel/oj-test-platform/actions/runs/37033319446)
恢复全绿，对应 `77ae90199a0bb8fc7b4eae7617e54df8b557aed2`；该次仍只有回归矩阵和 Docker Mock 作业。

## 完整四作业验收

[运行 37033913862](https://github.com/zhzgg123-pixel/oj-test-platform/actions/runs/37033913862)
对应 `f75c76e1e37d8a88136acf950f7946b06ebfb4aa`，Gitee/GitHub 阶段分支 SHA 一致。
Python 3.12/3.14 各 307 条通过，Docker 六条用例和重建持久化通过，真实 C++ 的 32 条测试全部通过且无跳过。
下载后核实 30 对 HTML/JSON、平台与 SUT SHA、两道题清理清单均一致，上传内容不含数据库或私有设置。
32 个任务包括 28 COMPLETED、2 个预期登录失败的 FAILED 和 2 个取消测试的 CANCELLED；这不等于测试失败。
原始制品下载保留在 `artifacts/ci-37033913862/`；较深路径在 Windows 上需短下载目录或长路径读取方式。
GitHub 制品保留 14 天，本地副本与仓库内脱敏摘要共同保留溯源信息。

准备阶段可能受Gitee网络影响。运行37034861698在clone时连接被重置，真实E2E未执行，不能认定通过。
没有私有设置时收集器只写固定NOT_RUN状态，然后失败退出；不上传未经脱敏的原始证据。
环境尚未准备则跳过Compose清理。诊断制品成功上传不改变原作业失败结论。
