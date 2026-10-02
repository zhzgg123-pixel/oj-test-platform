# 真实 C++ OJ 隔离联调

## 当前范围

S10a 建立固定源码、专用 MySQL、真实服务启动和登录检查。题目 seed、精确 cleanup、五种判题状态和并发矩阵将在 S10b 完成；基础设施健康不等于真实判题验收通过。

被测仓库：`https://gitee.com/chasing-dreams-zhuo/cpp-oj.git`，固定提交 `cede96af7ea62f07bc1fbc0c466658b771b57777`。检出放在忽略的 `.cache/cpp-oj`；原桌面 C++ 源码不变。准备脚本拒绝错误远端、错误 SHA 或已有修改，不执行 reset、clean 或覆盖已有源码。

## 准备和启动（PowerShell）

```powershell
powershell -NoProfile -File scripts/prepare_sut.ps1
docker compose --env-file .env.e2e -f compose.e2e.yaml config --quiet
docker compose --env-file .env.e2e -f compose.e2e.yaml build
docker compose --env-file .env.e2e -f compose.e2e.yaml up -d --wait
.\.venv\Scripts\python.exe -X utf8 scripts/e2e_environment.py --config config_center/e2e.example.yaml --evidence artifacts/s10a-environment.json
```

每条命令成功退出后才能继续。Linux 可用 `python scripts/prepare_e2e.py` 代替 PowerShell 包装脚本。

如果默认 Debian 源下载过慢，可使用 Debian 官方镜像列表中的上海交大镜像：`docker compose --env-file .env.e2e -f compose.e2e.yaml build --build-arg DEBIAN_MIRROR=mirror.sjtu.edu.cn`。该参数仅允许默认源和此镜像，保留 HTTPS 证书及 APT 签名校验；不改变固定的被测源码版本。构建证据应记录所用镜像源。

准备脚本在 `.env.e2e` 生成随机数据库和管理员密码，再次运行保留已有值；不要提交或打印该文件，也不要在保留数据卷时删除并重新生成它。Compose 必须显式传 `--env-file .env.e2e`。`config --quiet` 只验证结构；普通 config 输出会展开密码，不应保存为报告。

原始 schema 的默认数据库选择和默认管理员 INSERT 被移除，保留原表结构，并增加只有本环境使用的 `e2e_scope` 标识表。派生 SQL 和来源哈希在 `.cache/e2e`。应用自行创建专用随机密码管理员 `e2e_admin`，数据库固定为 `oj_platform_e2e`。

## 隔离与版本约束

- Compose 项目固定 `oj-platform-e2e`，专用内部网络和 MySQL 数据卷，不连接现有服务或共享数据库。C++ OJ 和 MySQL 仅连接内部网络。
- 单独的非 root Nginx gateway 同时连接内部网络和专用 ingress 网络，仅映射 `127.0.0.1:18090`；OJ 和 MySQL 都不直接发布端口。仅接入 internal 网络的容器在本次 Docker 环境中不会实际发布端口，因此入口单独设置，保持判题器网络隔离。代理关闭请求重试和访问日志。端口冲突时先查明占用，不能随意将测试重定向到别的服务。
- C++ 使用真实 g++ 编译/运行。镜像以 UID/GID 10001 运行，根文件系统只读；临时配置、源码和可执行文件放在 tmpfs。仅使用本项目受控测试模板，不把此进程级判题器视为可接收任意不可信代码的安全沙箱。
- 固定 Debian/MySQL 镜像摘要；APT 通过验证证书的 HTTPS 下载并保留 BuildKit 包缓存，构建阶段复用运行阶段的编译器依赖；构建从源码复制文件，不复制上游 config.json、.git 或本地凭据。编译参数将 httplib 初始线程数固定为 8，容器限制 2 CPU/1 GiB/256 PID，记录这些约束以解释并发结果。
- MySQL 8.0 的 native password 兼容选项用于该固定 Connector/C++ 1.x 测试环境，不是推荐生产部署的认证方案。

`e2e_environment.py` 在登录前校验容器项目/服务标签、健康状态、网络隔离、本机端口、镜像源码标签；再查询实际数据库名、部署标识、被测 SHA 和管理员存在性。最后使用本地随机凭据登录，检查 Cookie 和受保护的题目列表 API。输出仅包含脱敏身份信息，密码和 Cookie 不进入证据。

后续 seed/cleanup 必须复用这一验证，并用清单追踪精确题目 ID 和内容，禁止对共享数据执行重置。真实 E2E 必须通过 `--run-e2e --e2e-config config_center/e2e.example.yaml` 显式启用；目前未添加判题用例时，零条 E2E 应失败而非通过。

## 停止与保留

```powershell
docker compose --env-file .env.e2e -f compose.e2e.yaml down
```

普通 down 保留数据库和 `.env.e2e`。不要使用 down -v 作为题目清理步骤；后续 fixture cleanup 只删除该次清单里的数据。
