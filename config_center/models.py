"""One validated non-secret task configuration for Web, CLI and persistence."""
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class ValidatedModel(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True, validate_default=True)


def validate_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('OJ base URL must be HTTP or HTTPS with a host')
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise ValueError('OJ base URL must not contain credentials, query or fragment')
    if any(c.isspace() for c in value):
        raise ValueError('OJ base URL cannot contain whitespace')
    parsed.port  # Validate malformed and out-of-range ports.
    return value.rstrip('/')


class TaskConfig(ValidatedModel):
    adapter_name: str = Field(default='local_oj', pattern=r'^[a-zA-Z][a-zA-Z0-9_]*$')
    base_url: str = 'http://localhost:8080'
    profile_id: str = Field(default='a_plus_b', pattern=r'^[a-zA-Z0-9_-]+$')
    problem_id: str = Field(default='1', pattern=r'^[1-9][0-9]*$')
    strategies: list[Literal['random', 'boundary', 'rule']] = Field(
        default_factory=lambda: ['random', 'boundary', 'rule'], min_length=1)
    case_count: int = Field(default=5, ge=1, le=1000)
    seed: int = 42
    mode: Literal['sequential', 'concurrent'] = 'sequential'
    max_workers: int = Field(default=1, ge=1, le=16)
    request_timeout: float = Field(default=30, gt=0, allow_inf_nan=False,
                                    validation_alias=AliasChoices('request_timeout', 'timeout'))
    poll_interval: float = Field(default=1, gt=0, allow_inf_nan=False)
    poll_timeout: float = Field(default=60, gt=0, allow_inf_nan=False)

    _valid_url = field_validator('base_url')(validate_base_url)

    @field_validator('case_count', 'seed', 'max_workers', mode='before')
    @classmethod
    def reject_boolean_numbers(cls, value):
        if isinstance(value, bool):
            raise ValueError('boolean is not an integer setting')
        return value

    @field_validator('problem_id', mode='before')
    @classmethod
    def normalize_problem_id(cls, value):
        return str(value) if type(value) is int else value

    @model_validator(mode='after')
    def coherent_task(self):
        if len(set(self.strategies)) != len(self.strategies):
            raise ValueError('strategies must not contain duplicates')
        if self.case_count < len(self.strategies):
            raise ValueError('case_count must cover every selected strategy')
        if self.poll_timeout < self.poll_interval:
            raise ValueError('poll_timeout must be at least poll_interval')
        if self.mode == 'sequential':
            self.max_workers = 1
        return self

    @property
    def timeout(self):
        """Compatibility accessor; persisted name is request_timeout."""
        return self.request_timeout

    def to_dict(self):
        return self.model_dump(mode='json')

    def to_task_executor_config(self):
        """Compatibility method; credentials deliberately never enter this mapping."""
        return self.to_dict()


class ExecutionCredentials(ValidatedModel):
    username: str = ''
    password: SecretStr = Field(default='', exclude=True, repr=False)
