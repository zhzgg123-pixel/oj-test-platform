# OJ 自动化测试平台：实现说明

本文替代早期规划中的完成度描述，当前使用命令统一见 [README](README.md)，逐项验收见 [acceptance](docs/acceptance.md)。早期文档保留在 Git 历史，不作为现有功能证明。

## 架构

Web / CLI → TaskConfig → TaskService → ProfileLoader / CaseBuilder → SQLite 输入快照 → 顺序执行器或有界线程池 → 独立 Adapter / Session → OJ → JudgeOracle → 逐例持久化 → 一致快照 → HTML / JSON。

- FastAPI 与 CLI 使用同一配置模型和任务服务；配置非法、零用例或登录失败不能返回成功。
- YAML 定义两道不同题意、模板、限制和 fixtures；random/boundary/rule 按总数分配，seed 和源码哈希支持复现。
- LocalOJ 映射同步登录/提交回执，区分 verdict、HTTP 拒绝、业务拒绝、协议与传输错误；提交 POST 不透明重试。
- 线程池有界补位，每条用例独立会话；未认证规则使用无 Cookie 会话，结果按原输入归属保存。
- SQLite 的 tasks/task_cases/case_results/reports 记录完整证据；独占运行锁、短事务、WAL 和迁移保护历史。
- 报告从同一数据库快照生成，包含实际源码、预期/实际、错误、seed、profile/平台/SUT SHA；双格式和索引一致，HTML 转义、敏感字段脱敏。
- Docker 提供单进程非 root 平台和独立 Mock；真实 E2E 另启专用 MySQL、g++ OJ 与回环 gateway。
- GitHub Actions 用固定 Action SHA、依赖锁与最小权限执行回归、Docker 和真实判题，失败仍保留制品。

## 已验证范围

代码基线 `f75c76e1e37d8a88136acf950f7946b06ebfb4aa`：Windows 干净安装307条非E2E通过；Linux Python3.12/3.14各307条通过；真实C++32条通过并生成30对报告。
其中两个登录失败任务、两个取消任务是预期负向测试，JUnit 均通过。故意失败的独立CI分支证明测试失败时仍归档报告。
浏览器创建、详情、取消、报告和重启历史的实际操作证据见 [manual-web-checks](docs/manual-web-checks.md)；不是单靠静态代码或API测试推断。

## 可用于简历或面试的表述

基于 Python/FastAPI 构建 OJ 自动化测试平台，支持 YAML 题目配置及随机、边界、规则策略，统一 Web/CLI 任务入口；采用 SQLite 保存输入快照和逐例结果，通过独立会话的有界线程池执行判题断言，并生成可追溯的 HTML/JSON 报告。使用 pytest 与 HTTP Mock 覆盖故障和负向场景，结合 Docker、GitHub Actions 完成两道题和 AC/WA/CE/TLE/RE 的真实回归及制品归档。

解释随机策略时需说明是按 seed 抽样程序模板；解释并发时使用实测请求重叠与结果隔离，不编造 QPS 或效率提升百分比。

## 实现边界

只交付并实际适配了固定 LocalOJ 协议；没有注册流程自动化、任意OJ通用接入、多用户权限、分布式任务、Vue3或AI生成测试点的完成声明。
取消不保证杀死远端程序；MySQL服务与平台SQLite不同；真实判题使用受控模板，不是生产级任意代码安全沙箱。
报告文件和SQLite不是跨介质原子事务，强制断电可能留下未登记孤立文件。CLI中断自动测试使用Python触发中断，不等同所有终端的物理Ctrl+C验收。
上述能力无需Redis/Celery或新的前端框架；后续扩展应新增契约、验收和运行证据。
