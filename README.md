# OJ-Test-Platform

Python / FastAPI OJ 自动化测试平台，正在按已审计的简历能力清单逐步完善。

## 当前状态

当前为经过脱敏的原始源码基线，保留生成器、Adapter、顺序执行、Web/CLI 和基础报告。**SQLite、YAML 题目配置、完整并发入口、平台回归、Docker、CI 尚未验收完成**。

原始文档 `OJ测试开发工具.md` 是历史资料，其中完成度描述不作为当前能力证明。请以 [进度](docs/progress.md)、[原始审计](docs/initial-audit.md) 和对应测试证据为准。

## 开发环境

主验收 Python 3.12，另计划验证 3.14。Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

本基线没有平台自动化测试，不能以编译检查替代业务测试。后续 S01 引入 pytest 和独立 HTTP Mock。

## 开发约定

- 在本仓库开发，原始桌面源码保留；C++ OJ 继续由独立仓库管理。
- 不提交密码、Cookie、令牌、运行数据库或历史报告。已移除导入源码的默认密码。
- 按 [实施计划](docs/implementation-plan.md) 小步修改、测试、提交、推送，核对 Gitee 远端 SHA。
- 设计与验收口径见 [设计约定](docs/design-contract.md)。
