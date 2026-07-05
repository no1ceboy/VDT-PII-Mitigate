"""
Backwards compatibility stub for PII leakage evaluation.
Redirects AttackEvaluator imports to PIILeakageEvaluator.
"""

from .pii_leakage_evaluator import PIILeakageEvaluator as AttackEvaluator, EvaluationResult
from .pii_leakage_evaluator import PIILeakageEvaluator

__all__ = ["AttackEvaluator", "PIILeakageEvaluator", "EvaluationResult"]
