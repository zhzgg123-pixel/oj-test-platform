import pytest
from core_engine.case_engine.case_builder import CaseBuilder

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('spec', [{'strategies': []}, {'strategies': ['unknown']},
    {'strategies': ['random'], 'count': 0}])
def test_invalid_generation_spec_does_not_silently_produce_empty_result(spec):
    with pytest.raises(ValueError):
        CaseBuilder().build(spec)


def test_generator_failure_is_not_swallowed():
    class BrokenGenerator:
        def generate(self, spec):
            raise RuntimeError('generator failed')
    builder = CaseBuilder()
    builder.register_generator('broken', BrokenGenerator())
    with pytest.raises(RuntimeError, match='generator failed'):
        builder.build({'strategies': ['broken'], 'count': 1})


def test_empty_generator_output_is_not_success():
    class EmptyGenerator:
        def generate(self, spec):
            return []
    builder = CaseBuilder()
    builder.register_generator('empty', EmptyGenerator())
    with pytest.raises(ValueError, match='no cases'):
        builder.build({'strategies': ['empty'], 'count': 1})
