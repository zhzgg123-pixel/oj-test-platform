"""Detached report input read from one repository transaction."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReportArtifact:
    id: str
    format: str
    relative_path: str
    sha256: str


@dataclass(frozen=True)
class ReportSnapshot:
    task: Any
    cases: tuple

    def to_result(self):
        from core_engine.contracts import Observation
        from core_engine.executor.base_executor import TaskResult, CaseResult
        task = self.task
        result = TaskResult(total=task.counts['total'], passed=task.counts['passed'],
                            failed=task.counts['failed'], error=task.counts['error'],
                            cancelled=task.counts['cancelled'], start_time=task.started_at or task.created_at)
        for stored in self.cases:
            row = stored.result
            if row is None:
                continue
            actual = Observation(**row['actual']) if row['actual'] else None
            result.case_results.append(CaseResult(
                case=stored.to_case(), status=row['assertion_status'], observation=actual,
                actual_status=(actual.verdict or actual.error_code or f'HTTP_{actual.http_status}') if actual else '',
                error_message=row['reason'], start_time=row['started_at'], end_time=row['finished_at'],
                attempt_count=row['attempt_count']))
        result.remote_execution_may_continue = bool((task.error or {}).get('remote_execution_may_continue'))
        result.end_time = task.finished_at or max((r.end_time for r in result.case_results), default=result.start_time)
        return result

    def context(self):
        return {key: getattr(self.task, key) for key in
                ('id', 'name', 'profile', 'profile_sha256', 'platform_sha', 'sut_sha', 'created_at', 'started_at')}
