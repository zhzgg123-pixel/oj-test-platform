"""
报告生成器 - ReportGenerator

文档规范：
- generate(task_result, task_config) -> dict (含 report_id, json_path, html_path, summary)
- 数据含 status_distribution 和 failed_cases
- JSON + HTML 双格式
"""

from __future__ import annotations
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from core_engine.executor.base_executor import TaskResult, CaseResult

logger = logging.getLogger("oj.report")


class ReportGenerator:
    """报告生成器 - JSON + HTML 双格式"""

    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        task_result: TaskResult,
        task_config: Optional[dict] = None,
    ) -> dict:
        """
        生成测试报告（JSON + HTML）

        Args:
            task_result: 执行结果
            task_config: 任务配置（可选）

        Returns:
            dict: {"report_id", "json_path", "html_path", "summary"}
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_id = f"report_{timestamp}"

        data = self._build_data(report_id, task_result, task_config)

        # JSON 报告
        json_path = self.output_dir / f"{report_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # HTML 报告
        html_path = self.output_dir / f"{report_id}.html"
        html = self._render_html(data)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info("[Report] 报告已生成: %s, %s", json_path, html_path)

        return {
            "report_id": report_id,
            "json_path": str(json_path),
            "html_path": str(html_path),
            "summary": data["summary"],
        }

    def _build_data(
        self,
        report_id: str,
        tr: TaskResult,
        config: Optional[dict],
    ) -> dict:
        """构建报告数据"""
        # 状态分布统计
        dist: dict[str, int] = {}
        failed = []
        for cr in tr.case_results:
            s = cr.actual_status or cr.status
            dist[s] = dist.get(s, 0) + 1
            if not cr.passed:
                failed.append({
                    "case_id": cr.case.id,
                    "desc": cr.case.desc,
                    "expected": cr.case.expected_status,
                    "actual": cr.actual_status,
                    "error": cr.error_message,
                })

        return {
            "report_id": report_id,
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total": tr.total,
                "passed": tr.passed,
                "failed": tr.failed,
                "error": tr.error,
                "pass_rate": tr.pass_rate,
                "duration": tr.duration,
                "status_distribution": dist,
            },
            "config": config or {},
            "failed_cases": failed,
            "all_cases": [
                {
                    "id": cr.case.id,
                    "desc": cr.case.desc,
                    "expected": cr.case.expected_status,
                    "actual": cr.actual_status,
                    "status": cr.status,
                    "duration": cr.duration,
                }
                for cr in tr.case_results
            ],
        }

    @staticmethod
    def _render_html(data: dict) -> str:
        """渲染 HTML 报告"""
        s = data["summary"]
        rows = ""
        for cr in data["all_cases"]:
            icon = (
                "✅" if cr["status"] == "PASSED"
                else "❌" if cr["status"] == "FAILED"
                else "⚠️"
            )
            rows += (
                f"<tr><td>{cr['id']}</td>"
                f"<td>{cr['desc']}</td>"
                f"<td>{cr['expected']}</td>"
                f"<td>{cr['actual']}</td>"
                f"<td>{icon} {cr['status']}</td>"
                f"<td>{cr['duration']}s</td></tr>"
            )

        return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>OJ 测试报告</title>
<style>
body {{font-family:-apple-system,sans-serif;margin:20px;background:#f5f5f5;}}
.container {{max-width:1200px;margin:0 auto;background:#fff;padding:24px;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);}}
h1 {{color:#333;}}
.summary {{display:flex;gap:20px;margin:20px 0;}}
.stat {{flex:1;padding:16px;border-radius:8px;text-align:center;}}
.stat.total {{background:#e3f2fd;}}
.stat.passed {{background:#e8f5e9;}}
.stat.failed {{background:#fce4ec;}}
.stat .number {{font-size:28px;font-weight:bold;}}
.stat .label {{font-size:14px;color:#666;}}
.pass-rate {{font-size:36px;text-align:center;color:#4caf50;margin:16px 0;}}
table {{width:100%;border-collapse:collapse;margin-top:16px;}}
th,td {{padding:10px 12px;border-bottom:1px solid #eee;text-align:left;}}
th {{background:#fafafa;font-weight:600;color:#555;}}
tr:hover {{background:#f8f9fa;}}
</style></head><body><div class="container">
<h1>🔍 OJ 测试报告</h1>
<p>报告ID: {data['report_id']} | {data['generated_at']}</p>
<div class="pass-rate">通过率 {s['pass_rate']}%</div>
<div class="summary">
<div class="stat total"><div class="number">{s['total']}</div><div class="label">总用例</div></div>
<div class="stat passed"><div class="number">{s['passed']}</div><div class="label">通过</div></div>
<div class="stat failed"><div class="number">{s['failed']}</div><div class="label">失败</div></div>
<div class="stat error"><div class="number">{s['error']}</div><div class="label">错误</div></div>
</div>
<p>耗时: {s['duration']}s</p>
<table><thead><tr><th>用例ID</th><th>描述</th><th>预期</th><th>实际</th><th>状态</th><th>耗时</th></tr></thead><tbody>{rows}</tbody></table>
</div></body></html>"""

    def list_reports(self) -> list[dict]:
        """列出所有已生成的报告"""
        reports = []
        if not self.output_dir.exists():
            return reports
        for f in sorted(self.output_dir.iterdir(), key=os.path.getmtime, reverse=True):
            if f.suffix in (".json", ".html"):
                reports.append({
                    "filename": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "format": f.suffix[1:],
                })
        return reports

    def get_latest(self, fmt: str = "json") -> Optional[str]:
        """获取最新报告路径"""
        reports = [r for r in self.list_reports() if r["format"] == fmt]
        return reports[0]["path"] if reports else None
