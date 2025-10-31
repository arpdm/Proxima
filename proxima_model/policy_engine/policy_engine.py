"""
policy_engine.py

PROXIMA LUNAR SIMULATION - POLICY ENGINE

PURPOSE:
========
Extensible policy engine that centralizes scoring and applies operational policies
to the simulation world. Manages dynamic throttling and other adaptive behaviors
based on world system metrics.

ARCHITECTURE:
=============
- Policy Protocol: Interface for pluggable policies
- PolicyEngine: Central manager for policy registration and application
- Built-in Policies: Pre-configured policies like dust coverage throttling
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
import logging

from proxima_model.world_system.evaluation_engine import EvaluationResult
from proxima_model.policy_engine.policy_protocol import Policy
from proxima_model.policy_engine.environmental_policies import DustCoverageThrottlePolicy

logger = logging.getLogger(__name__)


class PolicyEngine:
    """
    Extensible policy engine that centralizes scoring and applies policies.

    How it operates:
    -----------------
    1.  The engine holds a list of registered policies (e.g., DustCoverageThrottlePolicy).
    2.  On each simulation step, the WorldSystem calls `apply_policies` with the
        complete `EvaluationResult` for that step.
    3.  The engine iterates through all enabled policies and calls their `apply` method,
        passing the `EvaluationResult`.
    4.  Each policy contains its own logic to analyze the metrics and scores within
        the `EvaluationResult` and determine what actions to take.
    5.  Actions are executed by calling methods on the simulation world, which is
        accessible to the policy via the engine instance (`engine.world`).
    6.  The engine collects and returns a dictionary of the effects from all
        applied policies.
    """

    def __init__(self, world):
        """
        Initialize policy engine with simulation world.

        Args:
            world: The simulation world object (WorldSystem)
        """
        self.world = world
        self._policies: List[Policy] = [
            DustCoverageThrottlePolicy(),  # Default policy
        ]

    def add_policy(self, policy: Policy) -> None:
        """
        Register a new policy with the engine.

        Args:
            policy: The policy object to add (must implement Policy protocol)
        """
        if not hasattr(policy, "id") or not hasattr(policy, "apply"):
            raise ValueError("Policy must implement Policy protocol (id, name, enabled, apply)")
        self._policies.append(policy)

    def remove_policy(self, policy_id: str) -> bool:
        """
        Remove a policy from the engine.

        Args:
            policy_id: The ID of the policy to remove

        Returns:
            True if policy was found and removed, False otherwise
        """
        original_length = len(self._policies)
        self._policies = [p for p in self._policies if getattr(p, "id", None) != policy_id]
        return len(self._policies) < original_length

    def enable_policy(self, policy_id: str, enabled: bool = True) -> bool:
        """
        Enable or disable a policy by its ID.

        Args:
            policy_id: The ID of the policy to enable/disable
            enabled: Whether to enable (True) or disable (False) the policy

        Returns:
            True if the policy was found and updated, False otherwise
        """
        for policy in self._policies:
            if getattr(policy, "id", None) == policy_id:
                policy.enabled = enabled
                return True
        return False

    def get_policy(self, policy_id: str) -> Optional[Policy]:
        """
        Get a policy by its ID.

        Args:
            policy_id: The ID of the policy to retrieve

        Returns:
            The policy object or None if not found
        """
        return next((p for p in self._policies if getattr(p, "id", None) == policy_id), None)

    def list_policies(self) -> List[Dict[str, Any]]:
        """
        List all registered policies and their status.

        Returns:
            List of dictionaries summarizing each policy
        """
        return [
            {
                "id": getattr(p, "id", None),
                "name": getattr(p, "name", "Unknown"),
                "enabled": getattr(p, "enabled", False),
            }
            for p in self._policies
        ]

    def apply_policies(self, evaluation_result: EvaluationResult) -> Dict[str, Any]:
        """
        Apply all enabled policies using the provided evaluation result.

        Args:
            evaluation_result: The complete evaluation result for the current step.

        Returns:
            Dictionary of effects from all applied policies, keyed by policy ID.
        """
        effects: Dict[str, Any] = {}

        for policy in self._policies:
            if not getattr(policy, "enabled", False):
                continue

            try:
                # Pass the evaluation_result directly to the policy
                result = policy.apply(self, evaluation_result)
                if isinstance(result, dict):
                    # Use policy ID for namespacing effects
                    effects[policy.id] = result
            except Exception as e:
                policy_id = getattr(policy, "id", "unknown")
                effects[policy_id] = {"error": str(e)}
                logger.error(f"Error applying policy {policy_id}: {e}", exc_info=True)

        return effects
