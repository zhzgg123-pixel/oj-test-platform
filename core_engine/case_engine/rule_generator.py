"""Explicit authentication and business rejection scenarios from YAML."""
from .base_generator import BaseGenerator
from .profile_generation import generate_profile_cases


class RuleGenerator(BaseGenerator):
    def generate(self, spec):
        return generate_profile_cases(spec, 'rule')
