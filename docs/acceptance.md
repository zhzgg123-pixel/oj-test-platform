# 简历能力与交付验收

验收日期：2026-10-03。已完整验收的运行代码基线为 `f75c76e1e37d8a88136acf950f7946b06ebfb4aa`。S12另补充准备失败时的安全状态制品；该修复已随a4571ab通过完整CI和下载制品验收，详见末尾记录。
固定真实SUT：`fa5ffe317f136f29039bc66e734fc687c4531e10`。需求来源为 [设计约定](design-contract.md) 和 [实施计划](implementation-plan.md)。

## 证据入口

- 完整四作业：[GitHub run 37033913862](https://github.com/zhzgg123-pixel/oj-test-platform/actions/runs/37033913862)。Linux Python3.12.14/3.14.7各307条；Docker smoke；真实C++32条，无跳过。
- 故意失败与归档：[run 37032980025](https://github.com/zhzgg123-pixel/oj-test-platform/actions/runs/37032980025)。唯一新增测试失败，报告生成/上传成功，门禁失败。
- 恢复绿色：[run 37033319446](https://github.com/zhzgg123-pixel/oj-test-platform/actions/runs/37033319446)。故意失败分支未合入main。
- 完整脱敏摘要：[evidence/index.json](evidence/index.json)；本地下载：`artifacts/ci-37033913862/`。GitHub制品保留14天，私有仓库需访问权限。
- 干净安装：独立clone `.cache/acceptance-f75c76e`、新建Python3.12.10虚拟环境，按锁文件安装和pip check均退出0；307条通过、32条未选中、1条上游弃用提示。日志 `artifacts/s12-clean-*`。

## 简历十项要求

下表的自动化测试均包含在上述基线的307条或32条测试中。PASS仅适用于对应层次。

| 要求 | 实现文件 | 关键测试或运行证据 | 状态 |
|---|---|---|---|
| YAML题目规则、三类策略 | `config_center/profile_loader.py`、`core_engine/case_engine/case_builder.py`、`profiles/*.yaml` | `tests/unit/test_profiles.py::test_two_problem_profiles_do_not_share_same_correct_solution`；`test_case_generation.py::test_seed_replays_exact_sources_and_expectations`；两题真实矩阵 | PASS |
| Adapter登录/提交/查询 | `plugins/local_oj/adapter.py`、`core_engine/api_client/request_client.py` | `tests/integration/test_local_adapter.py`、`test_retry_policy.py`；真实登录与五状态回执 | PASS |
| Web和CLI统一入口 | `config_center/models.py`、`task_center/service.py`、`backend/routers/task_router.py`、`main.py` | `test_entrypoints.py`、`test_durable_entrypoints.py`；[实际浏览器记录](manual-web-checks.md) | PASS |
| 顺序与线程池并发 | `core_engine/executor/sequential_executor.py`、`concurrent_executor.py` | `test_concurrency.py::test_scheduler_bounds_futures_and_isolates_sessions`；真实 `test_real_batch_results_and_http_overlap` | PASS |
| SQLite历史追溯 | `storage/database.py`、`storage/repository.py`、`task_center/runtime.py` | `test_durable_entrypoints.py::test_cli_task_is_queryable_from_web_in_next_process`；`test_restart_recovery.py::test_second_process_cannot_recover_live_owner_but_can_after_exit`；Windows/Linux均运行 | PASS |
| AC/WA/CE/TLE/RE严格校验 | `core_engine/assertion/judge_oracle.py`、`core_engine/contracts.py` | `test_judge_oracle.py::test_verdict_matrix`；`tests/e2e/test_real_oj.py::test_real_verdict`，两题×两模式×五状态20项 | PASS |
| 可复现HTML/JSON失败报告 | `core_engine/report_engine/report_generator.py`、`snapshot.py`、`core_engine/redaction.py` | `test_reports.py::test_report_preserves_reproduction_input_and_structured_difference`、`test_report_endpoints.py`、`test_redaction.py`；下载30对真实报告核对身份/计数 | PASS |
| pytest+HTTP Mock | `tests/mock_oj/server.py`、`tests/conftest.py` | `test_mock_harness.py`、`test_execution_assertions.py`；真HTTP、Cookie、故障注入和隔离清理 | PASS |
| Docker部署和持久化 | `Dockerfile`、`compose.yaml`、`scripts/smoke_compose.py` | CI docker-smoke job：create→down/up→verify，同一task和两格式哈希；镜像非root | PASS |
| GitHub Actions回归归档 | `.github/workflows/regression.yml`、`scripts/check_evidence.py`、`ci_demo.py`、`ci_e2e_artifacts.py` | 四作业实际运行、下载JUnit/HTML/JSON核验、独立故意失败红测及恢复绿色；两端源SHA一致 | PASS |

## 关键缺陷与约束复核

| 约束 | 当前验收依据 | 状态 |
|---|---|---|
| ERROR不能通配成功；未知判题/协议/网络异常不误通过 | Oracle负向矩阵、Adapter异常与执行断言测试 | PASS |
| 空策略/零用例/未知策略拒绝；登录失败非零退出 | TaskConfig及入口测试；真实两个登录失败任务 | PASS |
| HTTP200业务失败明确识别；同步回执不读共享最近结果 | LocalAdapter业务错误与乱序归属测试、真实32项 | PASS |
| GET受限重试；POST不重复提交 | `tests/integration/test_retry_policy.py` | PASS |
| 20等待任务、16worker上限、同库单运行进程 | 配置/队列满/并发future上界/真实子进程运行锁测试 | PASS |
| 取消停止补位，保留在途结果，终态不被覆盖 | `test_cancellation.py`和真实取消前后提交集合一致；2个CANCELLED任务 | PASS |
| 输入先保存、结果幂等、迁移保留历史、重启不重放 | Repository、lifecycle、restart、durable-entrypoints测试 | PASS |
| 报告同一快照、双格式索引事务、路径/哈希保护 | Repository快照与report-endpoints缺失/篡改/越界/回滚测试 | PASS |
| 密码/Cookie/令牌脱敏、HTML转义、安全DOM | redaction/reports测试及S08浏览器文本注入验证；CI只上传脱敏文本 | PASS |
| 原目录不覆盖；每阶段独立提交与远端核对 | S00来源清单和S00–S11证据记录，独立平台目录、SUT修复分支和固定checkout | PASS |
| 实际C++与MySQL，精确fixture清理 | 固定SHA环境检查、32项真实测试、30对报告；下载清单中两题均deleted | PASS |

## 实际执行和数据边界

真实32项的任务状态为28 COMPLETED、2 FAILED（预期登录失败）、2 CANCELLED。JUnit均通过；30对报告来自完成/取消任务，登录失败没有虚构报告。
GitHub runner从干净checkout安装、构建Docker和真实SUT，是Linux交付安装证据；Windows另做独立clone与全新venv回归。
平台SQLite只存平台任务；SUT MySQL是隔离被测系统。原桌面源码、旧SUT checkout和旧数据卷保留，不执行共享数据重置。

历史SUT `cede96af7ea62f07bc1fbc0c466658b771b57777` 的AC→MLE问题已保留失败证据；独立修复分支的 `fa5ffe3` 使用wait4统计具体子进程并校验毫秒CPU限制，47项judge和15项submit测试通过。
没有把旧失败当作平台通过，也没有通过放宽题目限制掩盖误判。

## 明确不作出的声明

- Mock不证明C++编译；HTTP请求重叠不证明吞吐、容量或性能提升百分比。
- 取消不保证终止远端程序；没有生产多用户权限或任意代码安全沙箱验收。
- 只有LocalOJ真实适配；没有注册测试、Vue3、Redis/Celery、分布式执行、AI用例生成的交付声明。
- 实际浏览器记录允许外部字体证书与favicon请求问题；不声称零控制台错误。
- 物理终端Ctrl+C的跨终端验证未执行；当前自动化通过Python中断触发验证退出130。
- 文件系统与SQLite不是同一事务；强制断电的孤立文件风险保留，不宣称断电原子性。

## 发布验收

S00–S12功能、安装与文档验收已完成；S12文档已通过链接/测试节点核验和独立审查。最终main与标签SHA须在发布操作后读回。
`v1.0.0` 只在最终交付提交的CI通过后创建；标签指向交付提交，运行链接和最终SHA记录在标签说明及本地验收摘要中。

## 后续运行中的启动故障

[main运行37034861698](https://github.com/zhzgg123-pixel/oj-test-platform/actions/runs/37034861698)
在Gitee源码clone时发生 `Recv failure: Connection reset by peer`，没有执行真实E2E，另三作业通过。
这是FAIL，不能用之前绿色覆盖。本次同时暴露了准备失败尚无.env时没有诊断制品的问题。
修复后只发布静态NOT_RUN状态并仍退出失败，不读取无法脱敏的文件；环境未创建时跳过Compose清理。
对应红测已复现缺少状态制品，修复在a4571ab的完整CI通过并核验制品。

## 发布候选复核

提交 `a4571abb70794eb46c991c342a7f24e4486228e7` 的
[run37036285779](https://github.com/zhzgg123-pixel/oj-test-platform/actions/runs/37036285779)
四作业全部通过。下载核验307×2非E2E、32真实E2E（无跳过）、30对真实报告、两题deleted清单和Docker报告哈希，均匹配该提交。
准备失败诊断修复随本次验证完成。最后的元数据提交只更新验收记录，最终发布SHA和对应CI URL由注释标签 `v1.0.0` 记录，避免在提交自身内容中伪造自引用SHA。
