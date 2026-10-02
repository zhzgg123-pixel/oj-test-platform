# Docker 安装与持久化验收

范围：Python 平台与 HTTP Mock；Mock 不编译 C++，不能代替真实 OJ 联调。
需要 Docker Compose v2 和 Linux 引擎。生产镜像使用 Python 3.12、运行依赖锁、UID/GID 10001 和单 Uvicorn worker；不包含 Git、开发虚拟环境、测试套件或历史报告。

## 从干净提交构建

在仓库根目录运行 PowerShell。先提交并审查改动，再使用该提交构建；不要给未提交的源码贴上旧 SHA。版本通过构建参数进入镜像标签及任务报告。省略版本仍可开发启动，但正式 smoke 会拒绝 `unknown`。

```powershell
git status --short
# 确认输出为空后继续。
$env:PLATFORM_SHA = (git rev-parse HEAD).Trim()
docker compose --profile demo config --quiet
docker compose --profile demo build
docker compose --profile demo up -d --wait platform mock-oj
docker compose --profile demo run --rm smoke --phase create
```

每条命令必须退出 0 后才能继续。启动时明确选择 platform 和 mock-oj；smoke 是一次性验收服务，用 run 调用，不随后台服务启动。

页面为 http://127.0.0.1:8000/frontend/index.html 。Mock 地址填 `http://mock-oj:8099`；演示账号 `tester / test-only` 只用于 Mock。Mock 不映射主机端口。平台默认只绑定回环地址；`.env.example` 可复制为本地 `.env` 调整端口和 OJ 地址。

不启用 demo 时，执行 `docker compose up -d --wait platform`，并配置容器可访问的真实 `OJ_BASE_URL`。容器里的 localhost 指向容器自身，不能用它访问主机 OJ。平台没有用户访问控制，此配置仅用于本机开发验收；对外部署需另行设计访问控制。

## 重启和容器重建

```powershell
docker compose restart platform
docker compose --profile demo run --rm smoke --phase verify
docker compose --profile demo down
docker compose --profile demo up -d --wait platform mock-oj
docker compose --profile demo run --rm smoke --phase verify
docker compose ps
docker compose images
```

SQLite、运行锁和报告位于命名卷 `platform-data` 的 `/data`。验收记录位于 `smoke-evidence` 的 `/evidence/smoke.json`。普通 down 保留卷；不要使用 down -v，它会删除历史和验收记录。

create 通过平台 HTTP API 创建 6 条用例，必须同时包含预期/实际 AC 和预期/实际 HTTP 401，全部断言通过，HTML/JSON 可下载且不含 Mock 密码。证据保存 task_id、版本、计数和两种报告 SHA256。verify 查询原任务并比较证据，不新建任务。单次总预算默认 60 秒，请求超时不超过 5 秒；任何错误退出 1。

create 拒绝覆盖已有证据。重复验收用 `--evidence /evidence/another-run.json`，随后 verify 必须传入相同路径。不要删除原证据来掩盖重启失败。可将记录导出到忽略的 artifacts 目录：

```powershell
docker compose --profile demo run --rm --no-deps --entrypoint python smoke -c "print(open('/evidence/smoke.json').read())"
```

## 依赖与证据边界

`requirements-runtime.lock` 仅包含运行依赖及其传递依赖。使用普通 uvicorn 的 asyncio 实现，不隐式安装 Linux uvloop；开发锁另含 pytest 等工具。构建运行 pip check。基础镜像固定 digest，升级须重新构建和验收。

Git SHA 由构建者声明，格式校验不能证明工作区干净，因此发布时同时保存源码提交、镜像 ID、容器健康状态和 smoke 输出。容器构建成功本身不代表 HTTP 任务成功。阶段结果见 `docs/progress.md` 和 `docs/evidence/index.json`。
