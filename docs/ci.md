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

真实 C++ E2E 作业、远端成功运行和故意失败后的制品归档验证仍待完成；不能仅凭工作流文件存在认定 CI 已验收。

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
