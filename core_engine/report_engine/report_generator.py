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
from dataclasses import asdict
from html import escape
from uuid import uuid4
from datetime import datetime
from pathlib import Path
from typing import Optional

from core_engine.executor.base_executor import TaskResult
from core_engine.redaction import redact, credential_values, safe_evidence

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
        *, task_context: Optional[dict] = None,
        secrets=(),
    ) -> dict:
        """
        生成测试报告（JSON + HTML）

        Args:
            task_result: 执行结果
            task_config: 任务配置（可选）

        Returns:
            dict: {"report_id", "json_path", "html_path", "summary"}
        """
        report_id = f"report_{uuid4()}"

        data = self._build_data(report_id, task_result, task_config)
        data['task'] = task_context or {}
        evidence_secrets = [secret for result in task_result.case_results if result.observation
                            for secret in credential_values(result.observation.evidence)]
        known_secrets = (*secrets, *evidence_secrets, *credential_values(task_config or {}), *credential_values(data))
        clean = redact(data, known_secrets)
        # Canonical identifiers, digests and enum verdicts are evidence, not secret
        # text. A coincidentally equal short password must not corrupt their schema.
        for key in ('report_id', 'generated_at'):
            clean[key] = data[key]
        for key in ('id', 'profile_sha256', 'platform_sha', 'sut_sha'):
            if key in data['task']:
                clean['task'][key] = data['task'][key]
        for raw, sanitized in zip(data['all_cases'], clean['all_cases']):
            sanitized['status'] = raw['status']
            for key in ('source_sha256', 'profile_sha256'):
                sanitized['input'][key] = raw['input'][key]
            if raw['expectation'] is not None:
                for key in ('kind', 'verdict', 'http_status'):
                    sanitized['expectation'][key] = raw['expectation'][key]
                if raw['expectation']['kind'] == 'verdict':
                    sanitized['expected'] = raw['expected']
            if raw['observation'] is not None:
                for key in ('kind', 'verdict', 'http_status'):
                    sanitized['observation'][key] = raw['observation'][key]
                if raw['observation']['kind'] == 'verdict':
                    sanitized['actual'] = raw['actual']
            sanitized['input']['source_redacted'] = raw['input']['code'] != sanitized['input']['code']
        clean['failed_cases'] = [case for raw, case in zip(data['all_cases'], clean['all_cases'])
                                if raw['status'] != 'PASSED']
        distribution = {}
        for case in clean['all_cases']:
            status = case['actual'] or case['status']
            distribution[status] = distribution.get(status, 0) + 1
        clean['summary']['status_distribution'] = distribution
        data = clean

        json_path = self.output_dir / f"{report_id}.json"
        html_path = self.output_dir / f"{report_id}.html"
        # Render both before touching disk; readers never observe a partial file.
        contents = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), self._render_html(data))
        paths = (json_path, html_path)
        staged = [path.with_suffix(path.suffix + '.tmp') for path in paths]
        published = []
        try:
            for path, content in zip(staged, contents):
                with path.open('x', encoding='utf-8') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            for source, target in zip(staged, paths):
                os.replace(source, target)
                published.append(target)
        except BaseException:
            for path in [*staged, *published]:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning('Report cleanup failed for %s', path.name)
            raise

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
        all_cases = []
        for cr in tr.case_results:
            s = cr.actual_status or cr.status
            dist[s] = dist.get(s, 0) + 1
            entry = {
                    "id": cr.case.id,
                    "case_id": cr.case.id,
                    "desc": cr.case.desc,
                    "expected": cr.case.expected_status,
                    "actual": cr.actual_status,
                    "error": cr.error_message,
                    "status": cr.status,
                    "duration": cr.duration,
                    "attempt_count": cr.attempt_count,
                    "started_at": cr.start_time,
                    "finished_at": cr.end_time,
                    "input": {key: getattr(cr.case, key) for key in
                              ('problem_id', 'code', 'lang', 'strategy', 'profile_id',
                               'profile_sha256', 'source_sha256', 'seed', 'auth_mode', 'request_overrides')},
                    "expectation": asdict(cr.case.expectation) if cr.case.expectation else None,
                    "observation": asdict(cr.observation) if cr.observation else None,
                }
            all_cases.append(entry)
            if entry['observation'] is not None:
                entry['observation']['evidence'] = safe_evidence(entry['observation']['evidence'])
            if not cr.passed:
                failed.append(entry)

        return {
            "report_id": report_id,
            "schema_version": 2,
            "generated_at": datetime.now().isoformat(),
            "remote_execution_may_continue": tr.remote_execution_may_continue,
            "summary": {
                "total": tr.total,
                "passed": tr.passed,
                "failed": tr.failed,
                "error": tr.error,
                "cancelled": tr.cancelled,
                "pass_rate": tr.pass_rate,
                "duration": tr.duration,
                "status_distribution": dist,
            },
            "config": {key: value for key, value in (config or {}).items() if key in {
                'adapter_name', 'base_url', 'profile_id', 'problem_id', 'strategies', 'case_count',
                'seed', 'mode', 'max_workers', 'request_timeout', 'poll_interval', 'poll_timeout'}},
            "failed_cases": failed,
            "all_cases": all_cases,
        }

    @staticmethod
    def _render_html(data: dict) -> str:
        """渲染 HTML 报告"""
        s = data["summary"]
        cancellation_note = ("远端程序可能仍在执行；取消仅停止平台继续提交。"
                             if data.get("remote_execution_may_continue") else "")
        rows = ""
        for cr in data["all_cases"]:
            text = {key: escape(str(value), quote=True) for key, value in cr.items()}
            icon = (
                "✅" if cr["status"] == "PASSED"
                else "❌" if cr["status"] == "FAILED"
                else "⚠️"
            )
            rows += (
                f"<tr><td>{text['id']}</td>"
                f"<td>{text['desc']}</td>"
                f"<td>{text['expected']}</td>"
                f"<td>{text['actual']}</td>"
                f"<td>{icon} {text['status']}</td>"
                f"<td>{text['duration']}s</td></tr>"
            )
            evidence = escape(json.dumps(cr, ensure_ascii=False, indent=2), quote=True)
            rows += f'<tr><td colspan="6"><details><summary>输入、预期、实际与错误</summary><pre>{evidence}</pre></details></td></tr>'
        context = escape(json.dumps({'task': data.get('task', {}), 'config': data['config']}, ensure_ascii=False, indent=2), quote=True)

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
pre {{white-space:pre-wrap;overflow-wrap:anywhere;}}
</style></head><body><div class="container">
<h1>🔍 OJ 测试报告</h1>
<p>{cancellation_note}</p>
<p>报告ID: {data['report_id']} | {data['generated_at']}</p>
<div class="pass-rate">通过率 {s['pass_rate']}%</div>
<div class="summary">
<div class="stat total"><div class="number">{s['total']}</div><div class="label">总用例</div></div>
<div class="stat passed"><div class="number">{s['passed']}</div><div class="label">通过</div></div>
<div class="stat failed"><div class="number">{s['failed']}</div><div class="label">失败</div></div>
<div class="stat error"><div class="number">{s['error']}</div><div class="label">错误</div></div>
<div class="stat cancelled"><div class="number">{s.get('cancelled', 0)}</div><div class="label">取消</div></div>
</div>
<p>耗时: {s['duration']}s</p>
<details><summary>任务配置和版本</summary><pre>{context}</pre></details>
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
