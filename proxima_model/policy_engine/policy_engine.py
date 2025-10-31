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
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Protocol
import logging

# No longer need to import all metric details here
from proxima_model.world_system.evaluation_engine import EvaluationResult

logger = logging.getLogger(__name__)


class Policy(Protocol):
    """Policy protocol for pluggable policies."""

    id: str
    name: str
    enabled: bool

    def apply(self, engine: "PolicyEngine", evaluation_result: EvaluationResult) -> Dict[str, Any]:
        """
        Apply the policy to the simulation world.

        Args:
            engine: The policy engine instance.
            evaluation_result: The complete evaluation result for the current step.

        Returns:
            Dictionary of policy effects.
        """
        ...


class DustCoverageThrottlePolicy(Policy):
    """Policy that throttles sectors based on dust coverage levels."""

    id = "PLCY-DUST-THROTTLE"
    name = "Dust Coverage Throttling"
    enabled = True

    # Default configuration
    DEFAULT_METRIC_ID = "IND-DUST-COV"
    DEFAULT_SECTORS = ["science", "manufacturing"]
    DEFAULT_THROTTLE_FACTOR = 0.8  # Maximum throttle when score = 0
    DEFAULT_THROTTLE_START = 0.7  # Start throttling at 90% of target

    def __init__(
        self,
        metric_id: str = DEFAULT_METRIC_ID,
        sectors: Optional[List[str]] = None,
        throttle_factor: float = DEFAULT_THROTTLE_FACTOR,
        throttle_start_ratio: float = DEFAULT_THROTTLE_START,  # New parameter
    ):
        """
        Initialize dust coverage throttle policy.

        Args:
            metric_id: The metric ID to monitor (default: "IND-DUST-COV")
            sectors: Sectors to throttle (default: ["science", "manufacturing"])
            throttle_factor: Maximum throttle factor when performance is worst (default: 0.9)
            throttle_start_ratio: Ratio of target where throttling begins (default: 0.9)
        """
        self.metric_id = metric_id
        self.sectors = sectors if sectors is not None else self.DEFAULT_SECTORS.copy()
        self.throttle_factor = throttle_factor
        self.throttle_start_ratio = throttle_start_ratio

    def apply(self, engine: "PolicyEngine", evaluation_result: EvaluationResult) -> Dict[str, Any]:
        """Apply dust coverage throttling policy using the provided evaluation result."""

        # Get current dust level from the evaluation result
        current_dust = evaluation_result.performance_metrics.get(self.metric_id)

        # Get the score and goal information from the evaluation result
        score_data = evaluation_result.scores.get(self.metric_id)

        if current_dust is None or score_data is None or score_data.get("goal") is None:
            logger.warning(f"⚠️ No dust data or goal available for {self.metric_id}")
            return {"error": f"No data or goal for {self.metric_id}"}

        target_dust = score_data["goal"]["target"]
        score = score_data["score"]

        # Calculate proactive throttling
        throttle_start_level = target_dust * self.throttle_start_ratio

        if current_dust <= throttle_start_level:
            current_throttle = 0.0
        else:
            # Linear throttling from start level to target
            range_val = target_dust - throttle_start_level
            if range_val > 0:
                excess_ratio = (current_dust - throttle_start_level) / range_val
                current_throttle = min(1.0, excess_ratio) * self.throttle_factor
            else:
                current_throttle = self.throttle_factor if current_dust >= target_dust else 0.0

        logger.info(
            f"🌪️ DUST POLICY: dust={current_dust:.3f}, target={target_dust:.3f}, start={throttle_start_level:.3f}, score={score:.3f}, throttle={current_throttle:.3f}"
        )

        # Apply throttling to configured sectors
        effects = {
            "metric_id": self.metric_id,
            "score": score,
            "throttle_factor": current_throttle,
            "applied_to": [],
        }

        for sector_name in self.sectors:
            sector = engine.world.sectors.get(sector_name)
            if sector and hasattr(sector, "set_throttle_factor"):
                sector.set_throttle_factor(current_throttle)
                effects["applied_to"].append(sector_name)
                logger.info(f"🔧 Set {sector_name} throttle to {current_throttle:.3f}")
            else:
                logger.warning(f"⚠️ Sector {sector_name} not found or doesn't support throttling")

        return effects


class PolicyEngine:
    """
    Extensible policy engine that centralizes scoring and applies policies.
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
