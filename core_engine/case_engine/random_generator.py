"""Seeded template sampling from problem YAML."""
from .base_generator import BaseGenerator
from .profile_generation import generate_profile_cases


class RandomGenerator(BaseGenerator):
    def generate(self, spec):
        return generate_profile_cases(spec, 'random')
