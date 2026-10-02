"""Ordered boundary submissions defined by the problem YAML."""
from .base_generator import BaseGenerator
from .profile_generation import generate_profile_cases


class BoundaryGenerator(BaseGenerator):
    def generate(self, spec):
        return generate_profile_cases(spec, 'boundary')
