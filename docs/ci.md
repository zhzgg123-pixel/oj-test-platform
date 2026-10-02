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

S11a 提供本地报告生成与证据门禁。GitHub Actions 工作流、Python 3.12/3.14 矩阵、
Docker smoke、真实 C++ E2E、远端成功运行和故意失败后的制品归档验证属于后续 S11 工作。
不能仅凭本地门禁通过认定 CI 已验收。
