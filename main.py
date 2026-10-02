"""
OJ 自动化测试平台 - 启动入口

用法:
    python main.py                          # 启动 Web 服务 (默认 0.0.0.0:8000)
    python main.py --port 9000              # 自定义端口
    python main.py --host 127.0.0.1         # 自定义地址

    python main.py --ci                     # CI 模式：不启动 Web 服务，直接运行测试
    python main.py --ci --problem 2         # 指定题目 ID
    python main.py --ci --strategies random boundary  # 指定策略
    python main.py --ci --output report.json          # 输出到文件
"""

import os
import sys
import json
import argparse

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import uvicorn
from backend.app import create_app


def main():
    parser = argparse.ArgumentParser(description="OJ Test Platform")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")
    parser.add_argument("--log-level", type=str, default="info")

    # CI 模式参数
    parser.add_argument("--ci", action="store_true", help="CI 模式：直接运行测试，不启动 Web 服务")
    parser.add_argument("--problem", type=str, default="1", help="题目 ID")
    parser.add_argument("--strategies", type=str, nargs="*",
                        default=["random", "boundary", "rule"], help="测试策略")
    parser.add_argument("--count", type=int, default=5, help="用例数量")
    parser.add_argument("--base-url", type=str, default="http://localhost:8080", help="OJ 地址")
    parser.add_argument("--username", type=str, default="admin", help="OJ 用户名")
    parser.add_argument("--password", type=str, default="", help="OJ 密码")
    parser.add_argument("--output", type=str, default=None, help="结果输出文件 (JSON)")

    args = parser.parse_args()

    if args.ci:
        # ---- CI 模式：不启动 Web 服务，直接运行测试 ----
        run_ci(args)
    else:
        # ---- Web 服务模式 ----
        run_server(args)


def run_ci(args: argparse.Namespace):
    """CI 模式：命令行直接运行测试"""
    from plugins.plugin_manager import PluginManager
    from core_engine.executor.task_executor import TaskExecutor
    from core_engine.report_engine.report_generator import ReportGenerator

    print(f"🧪 OJ Test Platform — CI Mode")
    print(f"   OJ:     {args.base_url}")
    print(f"   Problem: #{args.problem}")
    print(f"   Strategies: {', '.join(args.strategies)}")
    print(f"   Count:  {args.count}")
    print()

    # 初始化
    pm = PluginManager()
    executor = TaskExecutor()
    report_gen = ReportGenerator()

    # 执行
    config = {
        "plugin": "local_oj",
        "base_url": args.base_url,
        "problem_id": args.problem,
        "strategies": args.strategies,
        "case_count": args.count,
        "login_required": True,
        "username": args.username,
        "password": args.password,
    }

    try:
        result = executor.run_task(task_id="ci-run", config=config)
        print(f"\n📊 执行结果:")
        print(f"   {result.summary_line}")

        # 生成报告
        info = report_gen.generate(task_result=result, task_config=config)
        print(f"\n📋 报告:")
        print(f"   JSON: {info['json_path']}")
        print(f"   HTML: {info['html_path']}")

        # 输出到文件
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump({
                    "ci_run": True,
                    "config": config,
                    "result": {
                        "total": result.total,
                        "passed": result.passed,
                        "failed": result.failed,
                        "error": result.error,
                        "pass_rate": result.pass_rate,
                        "duration": result.duration,
                    },
                    "reports": info,
                }, f, ensure_ascii=False, indent=2)
            print(f"   📄 结果已输出: {args.output}")

        # CI 退出码：全部通过 → 0，有失败 → 1
        if result.failed > 0 or result.error > 0:
            print("\n❌ CI 检查未通过")
            sys.exit(1)
        else:
            print("\n✅ CI 检查通过")

    except Exception as e:
        print(f"\n💥 执行失败: {e}", file=sys.stderr)
        sys.exit(1)


def run_server(args: argparse.Namespace):
    """Web 服务模式"""
    app = create_app(config_path=args.config)

    from fastapi.staticfiles import StaticFiles
    frontend_dir = os.path.join(project_root, "frontend")
    reports_dir = os.path.join(project_root, "reports")

    if os.path.exists(frontend_dir):
        app.mount("/frontend", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    if os.path.exists(reports_dir):
        app.mount("/reports", StaticFiles(directory=reports_dir), name="reports")

    print(f"""
╔══════════════════════════════════════════╗
║     🧪 OJ 自动化测试平台已启动           ║
║──────────────────────────────────────────║
║  📊 前端:    http://localhost:{args.port}/frontend/index.html  ║
║  📋 API:     http://localhost:{args.port}/docs                 ║
║  🔌 插件:    local_oj                                    ║
║  ⚙️  配置:    {args.config or 'config.yaml'}             ║
╚══════════════════════════════════════════╝
    """)

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
