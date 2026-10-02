# OJ-Test-Platform

[![Platform regression](https://github.com/zhzgg123-pixel/oj-test-platform/actions/workflows/regression.yml/badge.svg)](https://github.com/zhzgg123-pixel/oj-test-platform/actions/workflows/regression.yml)

Python / FastAPI OJ 自动化测试平台：YAML 题目规则、三类用例策略、Web/CLI 共用任务服务、SQLite 历史、顺序/线程池并发和 HTML/JSON 报告。

已验证：Windows 干净安装 307 条非 E2E 回归；GitHub Linux Python 3.12/3.14 各 307 条；Docker 重建持久化；固定真实 C++ OJ 的 32 条测试和 30 对报告。
依据是 [完整 CI 运行](https://github.com/zhzgg123-pixel/oj-test-platform/actions/runs/37036285779) 的提交 `a4571abb70794eb46c991c342a7f24e4486228e7`。
[验收对照](docs/acceptance.md)区分 Mock、真实判题、浏览器和 CI；历史阶段记录见 [进度](docs/progress.md)。GitHub 为私有仓库，运行和制品需仓库访问权限。

## 1. 安装

从本仓库根目录执行 Windows PowerShell 命令。Python 3.12 为主验收版本，3.14 在 CI 验证。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -m "not e2e" -q
```

Linux 使用 `python3 -m venv .venv`，将后续解释器路径换为 `.venv/bin/python`。测试默认不访问真实 OJ；真实 E2E 需要显式启用。

## 2. 配置与题目

默认配置为 `config_center/config.yaml`，用 `--config` 选择文件。任务参数优先级：CLI 显式参数 > `OJ_*` 环境变量 > YAML > 默认值。
内置 `profiles/a_plus_b.yaml` 与 `profiles/max_of_two.yaml`，规则和模板格式见 [题目配置](profiles/README.md)。profile 决定题意，problem-id 必须使用目标 OJ 上对应题目的实际 ID。

`random` 按 seed 抽样程序模板，`boundary` 使用 CE/TLE/RE 等模板，`rule` 检查匿名、缺失题目、空源码。case-count 是三类策略合计的精确数量。
相同配置/seed 能复现实际提交源码；不是向任意 OJ 注入随机 stdin。两题 fixtures 是已部署题目数据的快照。

## 3. HTTP Mock

新开一个终端运行：

```powershell
.\.venv\Scripts\python.exe -m tests.mock_oj.server --port 8099
```

地址 `http://127.0.0.1:8099`，演示账号 `tester` / `test-only`。Mock 通过源码中的显式标记返回状态，不编译 C++；仅用于平台链路与故障注入测试。

## 4. Web

```powershell
.\.venv\Scripts\python.exe main.py --host 127.0.0.1 --port 8000 --db runtime/web.db --report-dir reports/web
```

浏览器打开 `http://127.0.0.1:8000/frontend/index.html`。填写 Mock 地址与演示账号，选择 a_plus_b、题号 1、策略、数量、seed 和顺序/并发模式即可创建任务。
页面支持取消、分页历史、逐例源码/预期/实际详情、HTML/JSON 下载和终态删除。重启时使用相同数据库和报告目录，可继续查询历史。

## 5. CLI

保持 Mock 运行，使用独立数据库避免与 Web 的执行锁冲突：

```powershell
$env:OJ_USERNAME = 'tester'
$env:OJ_PASSWORD = 'test-only'
.\.venv\Scripts\python.exe main.py --ci --base-url http://127.0.0.1:8099 --profile a_plus_b --problem-id 1 --strategies random rule --case-count 6 --seed 2 --mode concurrent --max-workers 2 --db runtime/cli.db --report-dir reports/cli
Remove-Item Env:OJ_PASSWORD
Remove-Item Env:OJ_USERNAME
```

上述凭据仅用于 Mock。真实密码通过环境变量传入，拒绝 `--password` 参数；不写入 TaskConfig、数据库或报告。
CLI 退出码：0 为非空任务全部断言通过且报告成功，1 为执行/断言失败，2 为配置或运行锁冲突，130 为用户中断。
需要查询这次 CLI 历史时，在 CLI 结束后用 `--db runtime/cli.db --report-dir reports/cli` 启动 Web。

## 6. Docker 与真实 OJ

Docker Desktop 需运行 Linux 引擎。从干净提交构建本机演示：

```powershell
$env:PLATFORM_SHA = (git rev-parse HEAD).Trim()
docker compose --profile demo build
docker compose --profile demo up -d --wait platform mock-oj
docker compose --profile demo run --rm smoke --phase create
```

create 拒绝覆盖旧清单，后续使用 `--phase verify` 验证持久化。具体重启/重建、健康检查和新清单路径见 [Docker 文档](docs/docker.md)。普通 `down` 保留卷，不使用 `down -v` 清除历史。

真实 C++ 联调的固定 SUT 为 `fa5ffe317f136f29039bc66e734fc687c4531e10`，按 [真实 OJ 文档](docs/e2e.md)准备专用数据库和容器后执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/e2e -m e2e --run-e2e --e2e-config config_center/e2e.example.yaml -q
```

fixture 自动创建两道题并精确清理；不要手工猜题号或把配置指向已有共享数据库。测试验证两题、顺序/并发、AC/WA/CE/TLE/RE、负向规则、会话隔离和取消。

## 7. CI 与证据

工作流 `.github/workflows/regression.yml` 在 push、pull_request、workflow_dispatch 运行，包含双 Python 回归、Docker smoke 和真实 C++ E2E 三类、共四个作业。
JUnit、实际 HTML/JSON 以及脱敏诊断作为制品保留 14 天。pytest 失败时报告步骤和上传仍运行，证据门禁不允许零测试、全跳过或缺失报告冒充通过。
独立故意失败分支已验证变红且仍归档，随后正常分支恢复绿色。复现命令及 run 链接见 [CI 文档](docs/ci.md)。

## 数据、状态与边界

平台 **SQLite** 保存任务、源码输入、逐例结果和报告索引；被测 C++ OJ 的 **MySQL** 保存用户、题目与判题数据，两者独立。
一个数据库只允许一个平台执行进程；默认单 Uvicorn worker、一个运行任务、最多20个等待任务、每任务最多16线程。升级前停止进程并备份数据库及报告目录。

COMPLETED 只表示执行结束；success 还要求 total>0、全部通过、报告完整且哈希匹配。未知判题/协议/传输错误不能因预期为 ERROR 而通过。
取消停止后续提交并保留在途结果，不保证终止已经提交到远端的程序。异常重启将遗留活动任务标为 INTERRUPTED，不自动重放提交。
HTML 动态内容转义，前端使用安全文本，报告保留源码/profile/平台/SUT 版本及结构化差异；需要脱敏的源码带标记。

本地平台绑定回环地址且没有多用户访问控制；并发重叠验证不等于性能容量报告。C++ 判题器仅使用受控测试模板，不声称可安全执行任意不可信代码。
仅 LocalOJ 适配器经过真实联调；插件接口不等于已兼容所有 OJ。前端为静态 HTML/JS，无 Vue、Redis、Celery 或分布式调度的交付声明。

排障见 [troubleshooting](docs/troubleshooting.md)，架构与面试说明见 [项目说明](OJ测试开发工具.md)。代码主远端为 Gitee `origin`，GitHub `github` 承载实际 Actions；每一步提交后核对两端 SHA。
