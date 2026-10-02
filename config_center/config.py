"""Validated YAML configuration with explicit file and environment precedence."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator

from config_center.models import TaskConfig, ValidatedModel, validate_base_url


class OJConfig(ValidatedModel):
    base_url: str = 'http://localhost:8080'
    timeout: float = Field(default=30, gt=0, allow_inf_nan=False)
    retry_count: int = Field(default=3, ge=1, le=3)
    retry_delay: float = Field(default=1, ge=0, allow_inf_nan=False)
    _valid_url = field_validator('base_url')(validate_base_url)


class JudgeConfig(ValidatedModel):
    poll_interval: float = Field(default=1, gt=0, allow_inf_nan=False)
    poll_timeout: float = Field(default=60, gt=0, allow_inf_nan=False)
    max_concurrent: int = Field(default=5, ge=1, le=16)


class TestConfig(ValidatedModel):
    log_level: str = 'INFO'
    report_dir: str = 'reports'
    case_strategies: list[str] = Field(default_factory=lambda: ['random', 'boundary', 'rule'])
    generate_case_count: int = Field(default=5, ge=1, le=1000)


class AppConfig(ValidatedModel):
    env: str = Field(default='dev', pattern=r'^[a-zA-Z0-9_-]+$')
    oj: OJConfig = Field(default_factory=OJConfig)
    judge: JudgeConfig = Field(default_factory=JudgeConfig)
    test: TestConfig = Field(default_factory=TestConfig)
    task: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_task_defaults(self):
        self.task_config()
        return self

    def task_config(self) -> TaskConfig:
        data = dict(base_url=self.oj.base_url, request_timeout=self.oj.timeout,
                    poll_interval=self.judge.poll_interval, poll_timeout=self.judge.poll_timeout,
                    max_workers=self.judge.max_concurrent, strategies=self.test.case_strategies,
                    case_count=self.test.generate_case_count)
        overrides = dict(self.task)
        if 'timeout' in overrides:
            if 'request_timeout' in overrides:
                raise ValueError('use only one timeout field')
            overrides['request_timeout'] = overrides.pop('timeout')
        data.update(overrides)
        return TaskConfig.model_validate(data)

    @classmethod
    def load(cls, env=None, config_path=None, environ=None, task_overrides=None):
        environment = dict(os.environ if environ is None else environ)
        selected_env = env or environment.get('OJ_ENV', 'dev')
        if not selected_env or not all(c.isalnum() or c in '_-' for c in selected_env):
            raise ValueError('invalid environment name')
        config_dir = Path(__file__).parent
        raw = cls._load_yaml(Path(config_path) if config_path is not None else config_dir / 'config.yaml')
        if config_path is None:
            overlay = config_dir / f'config.{selected_env}.yaml'
            if overlay.is_file():
                cls._deep_merge(raw, cls._load_yaml(overlay))
        if config_path is None or env is not None or 'OJ_ENV' in environment:
            raw['env'] = selected_env
        else:
            raw.setdefault('env', selected_env)
        mappings = {
            'OJ_BASE_URL': [('oj', 'base_url'), ('task', 'base_url')],
            'OJ_TIMEOUT': [('oj', 'timeout'), ('task', 'request_timeout')],
            'OJ_LOG_LEVEL': [('test', 'log_level')],
            'OJ_REPORT_DIR': [('test', 'report_dir')],
            'OJ_ENV': [('env',)],
            'OJ_CASE_COUNT': [('task', 'case_count')],
            'OJ_SEED': [('task', 'seed')],
            'OJ_MODE': [('task', 'mode')],
            'OJ_MAX_WORKERS': [('task', 'max_workers')],
            'OJ_PROFILE': [('task', 'profile_id')],
            'OJ_PROBLEM_ID': [('task', 'problem_id')],
            'OJ_POLL_INTERVAL': [('task', 'poll_interval')],
            'OJ_POLL_TIMEOUT': [('task', 'poll_timeout')],
            'OJ_STRATEGIES': [('task', 'strategies')],
        }
        for name, paths in mappings.items():
            if name not in environment:
                continue
            value = environment[name]
            if name == 'OJ_STRATEGIES':
                value = [v.strip() for v in value.split(',') if v.strip()]
            for keys in paths:
                node = raw
                for key in keys[:-1]:
                    node = node.setdefault(key, {})
                    if not isinstance(node, dict):
                        raise ValueError('configuration sections must be mappings')
                if keys == ('task', 'request_timeout'):
                    node.pop('timeout', None)
                node[keys[-1]] = value
        if task_overrides:
            task = raw.setdefault('task', {})
            if not isinstance(task, dict):
                raise ValueError('task configuration must be a mapping')
            if task_overrides.get('request_timeout') is not None:
                task.pop('timeout', None)
            task.update({k: v for k, v in task_overrides.items() if v is not None})
        return cls.model_validate(raw)

    @staticmethod
    def _load_yaml(path):
        with open(path, encoding='utf-8') as stream:
            raw = yaml.safe_load(stream)
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError('configuration document must be a mapping')
        return raw

    @staticmethod
    def _deep_merge(base, override):
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                AppConfig._deep_merge(base[key], value)
            else:
                base[key] = value


def load_task_config(config_path=None, env=None, overrides=None) -> TaskConfig:
    return AppConfig.load(config_path=config_path, environ=env, task_overrides=overrides).task_config()
