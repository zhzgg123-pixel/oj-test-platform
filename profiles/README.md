# 题目配置

每道题由一个 YAML 和若干 C++ 模板组成。`a_plus_b` 与 `max_of_two` 的正确解、错误解和题目输入／输出 fixture 不同；执行器不应按题目名称写分支。

`schema_version: 1` 包含：

- `id/title/language`：逻辑题目标识，不是远端数据库 ID。
- `time_limit_ms/memory_limit_kb/fixtures`：计划部署到隔离 OJ 的限制和测试数据快照；仅加载 YAML 不会修改远端 OJ。
- `strategies.random.templates`：按任务 seed 采样模板。
- `strategies.boundary.templates`：编译、执行时间、异常退出等提交边界，按序覆盖。
- `strategies.rule.scenarios`：匿名认证、缺失题号、空源码等明确拒绝。

每条定义必须指定 `path` 或 `source_code` 其中之一，并指定 `expected_verdict` 或完整 `expectation` 其中之一。路径必须位于 profiles 内。`request_overrides` 当前仅支持题号，不支持伪造平台结果。

`// verdict:AC` 等注释仅供 HTTP Mock 选择响应；真实 C++ OJ 会编译执行源码，不读取注释判题。真实判题能力需通过 S10 验收。

ProfileLoader 保存完整源码快照、每份源码 SHA256 和综合 profile SHA256。修改 YAML 或模板后，新任务取得新快照；已取得的快照不会随磁盘内容变化。

这里的随机生成指程序模板采样，并非向 OJ 任意注入随机 stdin。远端题号在创建任务时绑定。
