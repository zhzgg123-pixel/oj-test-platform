# Web 实际操作验收

## S08a 创建表单（2026-10-02）

环境：Windows、本机 Chromium（playwright-cli 命名会话 oj-s08a）、独立临时 SQLite 与真实 HTTP Mock。浏览器实际点击/填表/提交；之后通过 API 和 SQLite 核对持久化参数。没有连接真实 C++ OJ。

1. 打开 `/frontend/index.html` → 新建任务；题目配置加载两道题。
2. 选择 `max_of_two`，题号 `2`，随机策略，4 条用例，seed `917`；填入 Mock 地址与测试账户。
3. 选择并发，线程数 `3`，创建。返回 202，保存的配置一致，密码框清空。
4. 回到新建，切换顺序；线程输入禁用且变为 `1`；补测试密码并创建。保存模式为 sequential、线程数为 1。
5. 对 profile 请求注入 HTTP 503，错误文本包含 HTML 标签：页面以文本显示，创建按钮禁用；恢复接口并重试后可创建。
6. 取消全部策略选择再提交：页面显示明确错误，不创建任务。

结果：PASS。

- 并发任务：`e562c45b-40f6-45f6-a4b0-2c0790966f84`，COMPLETED。
- 顺序任务：`e2602f6d-5d26-4be3-8748-8e5fa47e1f40`，COMPLETED。
- 本机证据：`artifacts/s08a-browser/concurrent-form.png`、`smoke.js`、`errors.js`、`tasks.db`；这些运行产物不提交 Git。
- 观察到外部 Google 字体证书错误及 favicon 404，未阻止本次操作；不将其描述为零控制台错误。
- 自动化辅助脚本最初因请求上下文缺少 baseURL 和沙箱无 URL 全局而失败，修正为显式绝对地址后完成上述操作；这些失败不算平台缺陷。

## S08b 任务和历史（2026-10-02）

环境与 S08a 相同，使用新的隔离数据库 `artifacts/s08b-browser/tasks.db`，Mock 判题响应延迟 1 秒。

- 实际创建名称包含 `<img src=x onerror=alert(1)>` 的 40 用例并发任务，页面仅显示文本，没有对应 img 节点；活动任务删除按钮禁用。
- 点击取消后观察 CANCEL_REQUESTED，再观察 CANCELLED、100% 进度；打开详情核对 40 条记录及实际源码。
- 通过页面链接分别打开 HTML/JSON 报告新标签，核对实际正文。
- 页面刷新后任务仍可查询；停止平台进程再启动，以新地址打开页面，原任务及 40 条用例历史仍可读取。
- 慢列表测试将响应延迟 3500ms：修复前持续丢弃响应，10秒内无任务行；改为请求完成后安排下一次轮询，干净浏览器重测通过。

结果：PASS。任务 ID `d9fbbb75-5027-418a-b888-790ffee0f462`。

可复用浏览器检查：`tests/browser/task-workflow.js`、`tests/browser/slow-polling.js`。运行前需启动平台/延迟 Mock，在页面新建标签填写实际 Mock 地址；脚本使用测试账户 tester/test-only，仅用于本地 Mock。通过 `playwright-cli -s=<session> run-code --filename=<script>` 执行。慢列表检查需要数据库中至少一条任务。

截图：`artifacts/s08b-browser/restarted-detail.png`，已打开核对。首次在报告弹窗返回后截取的整页图未展示详情，不作为验收截图。仍有外部字体证书和 favicon 请求错误，不计为业务流程失败，也不声称零控制台错误。

页面取消直接提交请求，提示等待在途请求结束；删除仍需确认。详情提供“刷新详情”，列表自动轮询。分页与动态文本渲染经代码审查；真实 C++ OJ 和跨机器部署仍由后续阶段验收。
