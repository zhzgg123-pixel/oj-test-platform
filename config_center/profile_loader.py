"""Validated problem profiles and self-contained, hashable source snapshots."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Literal, Mapping

from pydantic import Field, model_validator
import yaml

from config_center.models import ValidatedModel


class Fixture(ValidatedModel):
    stdin: str
    stdout: str


class CaseTemplate(ValidatedModel):
    name: str = ''
    path: str | None = None
    source_code: str | None = None
    expected_verdict: Literal['AC', 'WA', 'CE', 'TLE', 'RE', 'MLE'] | None = None
    expectation: dict | None = None
    auth_mode: Literal['authenticated', 'anonymous'] = 'authenticated'
    request_overrides: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode='after')
    def unambiguous_case(self):
        if (self.path is None) == (self.source_code is None):
            raise ValueError('exactly one of path or source_code is required')
        if (self.expected_verdict is None) == (self.expectation is None):
            raise ValueError('exactly one explicit expectation is required')
        self.expectation_value()
        if set(self.request_overrides) - {'problem_id'}:
            raise ValueError('only problem_id request overrides are supported')
        if 'problem_id' in self.request_overrides:
            value = self.request_overrides['problem_id']
            if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 2147483647:
                raise ValueError('problem_id override must be a positive signed 32-bit integer')
        return self

    def expectation_value(self):
        from core_engine.contracts import Expectation
        try:
            return (Expectation(kind='verdict', verdict=self.expected_verdict)
                    if self.expected_verdict is not None else Expectation(**self.expectation))
        except (TypeError, ValueError) as exc:
            raise ValueError('invalid explicit expectation') from exc


class TemplateStrategy(ValidatedModel):
    templates: list[CaseTemplate] = Field(min_length=1)


class RuleStrategy(ValidatedModel):
    scenarios: list[CaseTemplate] = Field(min_length=1)


class Strategies(ValidatedModel):
    random: TemplateStrategy
    boundary: TemplateStrategy
    rule: RuleStrategy


class ProfileDefinition(ValidatedModel):
    schema_version: Literal[1]
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$')
    title: str = Field(min_length=1)
    language: Literal['cpp'] = 'cpp'
    time_limit_ms: int = Field(default=1000, gt=0)
    memory_limit_kb: int = Field(default=65536, gt=0)
    fixtures: list[Fixture] = Field(min_length=1)
    strategies: Strategies


@dataclass(frozen=True)
class ProblemProfile:
    _definition_json: str
    template_sources: Mapping[str, str]
    source_hashes: Mapping[str, str]
    yaml_sha256: str
    profile_sha256: str

    @property
    def definition(self):
        # A caller changing a model cannot mutate the persisted replay snapshot.
        return ProfileDefinition.model_validate_json(self._definition_json)

    @property
    def id(self):
        return self.definition.id

    def to_dict(self):
        return {'definition': json.loads(self._definition_json),
                'template_sources': dict(self.template_sources), 'source_hashes': dict(self.source_hashes),
                'yaml_sha256': self.yaml_sha256, 'profile_sha256': self.profile_sha256}


class ProfileLoader:
    def __init__(self, root=None):
        self.root = (Path(root) if root is not None else Path(__file__).resolve().parents[1] / 'profiles').resolve()

    def _contained_file(self, relative):
        path = Path(relative)
        if path.is_absolute() or path.drive or '..' in path.parts:
            raise ValueError('profile paths must be relative and remain inside profiles directory')
        resolved = (self.root / path).resolve()
        if not resolved.is_relative_to(self.root) or not resolved.is_file():
            raise ValueError('profile or template file is missing or outside profiles directory')
        return resolved

    def load(self, profile_id: str) -> ProblemProfile:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', profile_id):
            raise ValueError('invalid profile_id')
        text = self._contained_file(profile_id + '.yaml').read_text(encoding='utf-8')
        try:
            raw = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError('invalid profile YAML') from exc
        definition = ProfileDefinition.model_validate(raw)
        if definition.id != profile_id:
            raise ValueError('profile id must match its filename')
        sources = {}
        candidates = (definition.strategies.random.templates + definition.strategies.boundary.templates
                      + definition.strategies.rule.scenarios)
        for item in candidates:
            if item.path is not None:
                sources[item.path] = self._contained_file(item.path).read_text(encoding='utf-8')
        hashes = {path: hashlib.sha256(source.encode('utf-8')).hexdigest() for path, source in sources.items()}
        yaml_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
        definition_json = definition.model_dump_json()
        canonical = json.dumps({'definition': json.loads(definition_json), 'sources': sources,
                                'yaml_sha256': yaml_hash}, sort_keys=True, ensure_ascii=False).encode('utf-8')
        return ProblemProfile(definition_json, MappingProxyType(sources), MappingProxyType(hashes),
                              yaml_hash, hashlib.sha256(canonical).hexdigest())
