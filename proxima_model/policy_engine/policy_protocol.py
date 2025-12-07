"""
policy_protocol.py

Defines the core `Policy` protocol for the simulation.
"""

from __future__ import annotations
from typing import Dict, Any, Protocol, TYPE_CHECKING

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from .policy_engine import PolicyEngine
    from ..world_system.evaluation_engine import EvaluationResult


class Policy(Protocol):
    """Policy protocol for pluggable policies."""

    id: str
    name: str
    enabled: bool

    def apply(self, engine: "PolicyEngine", evaluation_result: "EvaluationResult") -> Dict[str, Any]:
        """
        Apply the policy to the simulation world.

        Args:
            engine: The policy engine instance.
            evaluation_result: The complete evaluation result for the current step.

        Returns:
            Dictionary of policy effects.
        """
        ...
