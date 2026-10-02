"""
配置中心 - AppConfig

职责：
- 加载 YAML 配置文件
- 支持多环境（dev / prod）
- 支持环境变量覆盖
- 类型安全的 dataclass 输出
"""

from __future__ import annotations
import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OJConfig:
    base_url: str = "http://localhost:8080"
    timeout: int = 30
    retry_count: int = 3
    retry_delay: float = 1.0


@dataclass
class JudgeConfig:
    poll_interval: float = 1.0
    poll_timeout: int = 60
    max_concurrent: int = 5


@dataclass
class TestConfig:
    log_level: str = "INFO"
    report_dir: str = "reports"
    case_strategies: list[str] = field(default_factory=lambda: ["random", "boundary", "rule"])
    generate_case_count: int = 5


@dataclass
class AppConfig:
    """全局配置聚合"""

    env: str = "dev"
    oj: OJConfig = field(default_factory=OJConfig)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    test: TestConfig = field(default_factory=TestConfig)

    @classmethod
    def load(cls, env: Optional[str] = None) -> AppConfig:
        """
        加载配置，优先级：环境变量 > 环境文件 > 默认文件

        加载顺序:
        1. config.yaml (基础默认值)
        2. config.{env}.yaml (环境覆盖)
        3. 环境变量 OJ_BASE_URL 等 (运行时覆盖)
        """
        config_dir = Path(__file__).parent
        env = env or os.getenv("OJ_ENV", "dev")

        # 1. 加载默认配置
        raw = cls._load_yaml(config_dir / "config.yaml")

        # 2. 加载环境配置（合并覆盖）
        env_path = config_dir / f"config.{env}.yaml"
        if env_path.exists():
            cls._deep_merge(raw, cls._load_yaml(env_path))

        # 3. 环境变量覆盖
        cls._apply_env_overrides(raw)

        return cls._from_dict(raw)

    @staticmethod
    def _load_yaml(path: Path) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> None:
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                AppConfig._deep_merge(base[k], v)
            else:
                base[k] = v

    @staticmethod
    def _apply_env_overrides(config: dict) -> None:
        mappings = [
            ("OJ_BASE_URL", ("oj", "base_url")),
            ("OJ_TIMEOUT", ("oj", "timeout")),
            ("OJ_LOG_LEVEL", ("test", "log_level")),
            ("OJ_ENV", ("env",)),
        ]
        for var, keys in mappings:
            value = os.getenv(var)
            if value is not None:
                target = config
                for k in keys[:-1]:
                    target = target.setdefault(k, {})
                target[keys[-1]] = value

    @classmethod
    def _from_dict(cls, data: dict) -> AppConfig:
        return AppConfig(
            env=data.get("env", "dev"),
            oj=OJConfig(**data.get("oj", {})),
            judge=JudgeConfig(**data.get("judge", {})),
            test=TestConfig(**data.get("test", {})),
        )
