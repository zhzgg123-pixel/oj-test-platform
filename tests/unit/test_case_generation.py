"""Generated submissions must come from their selected profile and be replayable."""
import hashlib
from collections import Counter

import pytest

from config_center.models import TaskConfig
from config_center.profile_loader import ProfileLoader
from core_engine.case_engine.case_builder import CaseBuilder

pytestmark = pytest.mark.unit


def test_total_count_is_distributed_across_selected_strategies():
    config = TaskConfig(case_count=8)
    cases = CaseBuilder().build(config, ProfileLoader().load('a_plus_b'))
    assert len(cases) == 8
    assert Counter(case.strategy for case in cases) == {'random': 3, 'boundary': 3, 'rule': 2}
    assert len({case.id for case in cases}) == 8
    assert all(case.profile_sha256 and case.seed == 42 for case in cases)


def test_seed_replays_exact_sources_and_expectations():
    profile = ProfileLoader().load('a_plus_b')
    config = TaskConfig(strategies=['random'], case_count=20, seed=17)
    first = CaseBuilder().build(config, profile)
    second = CaseBuilder().build(config, profile)
    different = CaseBuilder().build(config.model_copy(update={'seed': 18}), profile)
    snapshot = lambda cases: [(c.source_sha256, c.expectation) for c in cases]
    assert snapshot(first) == snapshot(second)
    assert snapshot(first) != snapshot(different)
    assert all(c.source_sha256 == hashlib.sha256(c.source_code.encode()).hexdigest() for c in first)


def test_profile_selects_correct_program_even_with_same_remote_problem_id():
    loader = ProfileLoader()
    config = TaskConfig(strategies=['random'], case_count=1, seed=42)
    plus = CaseBuilder().build(config, loader.load('a_plus_b'))[0]
    maximum_config = config.model_copy(update={'profile_id': 'max_of_two'})
    maximum = CaseBuilder().build(maximum_config, loader.load('max_of_two'))[0]
    assert plus.source_code == loader.load('a_plus_b').template_sources['templates/a_plus_b/ac.cpp']
    assert maximum.source_code == loader.load('max_of_two').template_sources['templates/max_of_two/ac.cpp']
    assert plus.source_sha256 != maximum.source_sha256


def test_rules_have_explicit_auth_and_error_expectations():
    cases = CaseBuilder().build(TaskConfig(strategies=['rule'], case_count=3), ProfileLoader().load('a_plus_b'))
    assert cases[0].auth_mode == 'anonymous'
    assert cases[0].expectation.http_status == 401
    assert cases[1].problem_id == '2147483647'
    assert cases[1].request_overrides == {'problem_id': '2147483647'}
    assert cases[1].expectation.error_code == 'PROBLEM_NOT_FOUND'
    assert cases[2].source_code == ''
    assert cases[2].expectation.error_code == 'CODE_REQUIRED'


def test_profile_mismatch_is_rejected():
    with pytest.raises(ValueError, match='profile'):
        CaseBuilder().build(TaskConfig(), ProfileLoader().load('max_of_two'))
