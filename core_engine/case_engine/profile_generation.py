"""Materialize actual submitted source from a validated profile snapshot."""
import random

from config_center.models import TaskConfig
from config_center.profile_loader import ProfileLoader
from .base_generator import TestCase


def generate_profile_cases(spec, strategy):
    config = spec.get('config') or TaskConfig(
        profile_id=spec.get('profile_id', 'a_plus_b'), problem_id=spec.get('problem_id', '1'),
        strategies=[strategy], case_count=spec.get('count', 5), seed=spec.get('seed', 42))
    profile = spec.get('profile') or ProfileLoader().load(config.profile_id)
    definition = profile.definition
    group = getattr(definition.strategies, strategy)
    candidates = list(group.scenarios if strategy == 'rule' else group.templates)
    if spec.get('statuses') is not None:
        candidates = [c for c in candidates if c.expected_verdict in spec['statuses']]
    if not candidates:
        raise ValueError('no cases match selected profile templates')
    rng = spec.get('rng') or random.Random(config.seed)
    cases = []
    for index in range(spec.get('count', config.case_count)):
        template = rng.choice(candidates) if strategy == 'random' else candidates[index % len(candidates)]
        source = profile.template_sources[template.path] if template.path is not None else template.source_code
        expected = template.expectation_value()
        actual_problem = template.request_overrides.get('problem_id', config.problem_id)
        cases.append(TestCase(
            id=f'{config.profile_id}-{strategy}-{index + 1:04d}',
            desc=f'{definition.title}: {template.name or strategy}', problem_id=actual_problem,
            code=source, lang=definition.language, expectation=expected,
            expected_status=expected.verdict or expected.error_code or f'HTTP_{expected.http_status}',
            tags=[strategy, expected.kind], strategy=strategy, profile_id=config.profile_id,
            profile_sha256=profile.profile_sha256, seed=config.seed,
            auth_mode=template.auth_mode, request_overrides=dict(template.request_overrides),
            metadata={'generator': strategy, 'seed': config.seed, 'template_path': template.path,
                      'profile_id': config.profile_id, 'profile_sha256': profile.profile_sha256}))
    return cases
