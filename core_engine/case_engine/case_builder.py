"""Distribute a task's total case count across selected profile strategies."""
import random

from config_center.models import TaskConfig
from config_center.profile_loader import ProfileLoader
from .random_generator import RandomGenerator
from .boundary_generator import BoundaryGenerator
from .rule_generator import RuleGenerator


class CaseBuilder:
    def __init__(self):
        self._generators = {'random': RandomGenerator(), 'boundary': BoundaryGenerator(), 'rule': RuleGenerator()}

    def build(self, config, profile=None):
        if isinstance(config, dict):
            spec = dict(config)
            strategies = spec.get('strategies', ['random', 'boundary', 'rule'])
            count = spec.get('count', spec.get('case_count', 5))
            if not isinstance(strategies, list) or not strategies:
                raise ValueError('at least one strategy is required')
            if type(count) is not int or not 1 <= count <= 1000:
                raise ValueError('count must be an integer between 1 and 1000')
            if any(name not in self._generators for name in strategies):
                raise ValueError('unknown strategy')
            # Keep the explicit extension API for callers of registered custom generators.
            if any(name not in {'random', 'boundary', 'rule'} for name in strategies):
                cases = []
                for name in strategies:
                    generated = self._generators[name].generate(spec)
                    if not generated:
                        raise ValueError('strategy generated no cases')
                    cases.extend(generated)
                return cases
            spec.pop('count', None)
            spec['case_count'] = count
            config = TaskConfig.model_validate(spec)
        profile = profile or ProfileLoader().load(config.profile_id)
        if profile.id != config.profile_id:
            raise ValueError('task profile_id does not match loaded profile')
        rng = random.Random(config.seed)
        groups = {}
        for offset, name in enumerate(config.strategies):
            count = config.case_count // len(config.strategies) + (offset < config.case_count % len(config.strategies))
            groups[name] = self._generators[name].generate(
                {'config': config, 'profile': profile, 'count': count, 'rng': rng})
        # Round-robin order also makes partial/cancelled executions cover strategies early.
        cases = []
        for ordinal in range(config.case_count):
            strategy = config.strategies[ordinal % len(config.strategies)]
            case = groups[strategy][ordinal // len(config.strategies)]
            case.metadata['ordinal'] = ordinal
            cases.append(case)
        return cases

    def register_generator(self, name, generator):
        self._generators[name] = generator
