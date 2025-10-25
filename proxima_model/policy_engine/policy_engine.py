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

from proxima_model.policy_engine.metrics import (
    MetricType,
    GoalDirection,
    PerformanceGoal,
    MetricDefinition,
    MetricScore,
)

logger = logging.getLogger(__name__)


class Policy(Protocol):
    """Policy protocol for pluggable policies."""

    id: str
    name: str
    enabled: bool

    def apply(self, engine: "PolicyEngine") -> Dict[str, Any]:
        """
        Apply the policy to the simulation world.

        Args:
            engine: The policy engine instance

        Returns:
            Dictionary of policy effects
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
    DEFAULT_THROTTLE_FACTOR = 0.2  # Maximum throttle when score = 0

    def __init__(
        self,
        metric_id: str = DEFAULT_METRIC_ID,
        sectors: Optional[List[str]] = None,
        throttle_factor: float = DEFAULT_THROTTLE_FACTOR,
    ):
        """
        Initialize dust coverage throttle policy.

        Args:
            metric_id: The metric ID to monitor (default: "IND-DUST-COV")
            sectors: Sectors to throttle (default: ["science", "manufacturing"])
            throttle_factor: Maximum throttle factor when performance is worst (default: 0.75)
        """
        self.metric_id = metric_id
        self.sectors = sectors if sectors is not None else self.DEFAULT_SECTORS.copy()
        self.throttle_factor = throttle_factor

    def apply(self, engine) -> Dict[str, Any]:
        """Apply dust coverage throttling policy using the scoring mechanism."""

        # Get normalized score (0.0 = worst, 1.0 = best performance)
        score = engine.score(self.metric_id)

        if score is None:
            print(f"⚠️ No score available for {self.metric_id}")
            return {"error": f"No score available for {self.metric_id}"}

        # Calculate throttle factor
        current_throttle = (1.0 - score) * self.throttle_factor
        current_dust = engine.world.get_performance_metric(self.metric_id)

        print(f"🌪️ DUST POLICY: dust={current_dust:.2f}, score={score:.3f}, throttle={current_throttle:.3f}")

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
                print(f"🔧 Set {sector_name} throttle to {current_throttle:.3f}")
            else:
                print(f"⚠️ Sector {sector_name} not found or doesn't support throttling")

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

        self._metric_scores: Dict[str, Optional[float]] = {}
        self._goals_by_metric: Dict[str, PerformanceGoal] = {}
        self._rebuild_goal_cache()

    def _rebuild_goal_cache(self) -> None:
        """Rebuild the goals-by-metric lookup cache."""
        self._goals_by_metric = {goal.metric_id: goal for goal in self.world.performance_goals if goal.metric_id}

    def update_scores(self) -> None:
        """
        Update all metric scores based on current performance goals.

        This should be called once per step before applying policies.
        """
        # Rebuild goal cache in case goals changed
        self._rebuild_goal_cache()

        # Calculate scores for all metrics with goals
        self._metric_scores.clear()
        for metric_id, goal in self._goals_by_metric.items():
            score = self._calculate_score(metric_id, goal)
            self._metric_scores[metric_id] = score

    def _calculate_score(self, metric_id: str, goal: PerformanceGoal) -> Optional[float]:
        """
        Calculate score for a single metric based on its goal.

        Args:
            metric_id: The metric ID to score
            goal: The performance goal for this metric

        Returns:
            Score from 0.0 (worst) to 1.0 (best), or None if calculation fails
        """
        try:
            current_value = float(self.world.get_performance_metric(metric_id))
            target_value = goal.target_value
            direction = goal.direction

            if target_value == 0:
                return 1.0

            if direction == GoalDirection.MINIMIZE.value:
                # Lower values are better - score based on how close to target
                if current_value <= target_value:
                    return 1.0  # At or below target = perfect
                else:
                    # Score decreases as we get further from target
                    deviation_ratio = min(2.0, current_value / target_value)  # Cap at 2x target
                    return max(0.0, 2.0 - deviation_ratio)  # 1.0 at target, 0.0 at 2x target

            elif direction == GoalDirection.MAXIMIZE.value:
                # Higher values are better
                if current_value >= target_value:
                    return 1.0  # At or above target = perfect
                else:
                    # Score decreases as we get further from target
                    achievement_ratio = current_value / target_value
                    return max(0.0, min(1.0, achievement_ratio))

            return None

        except (ValueError, KeyError, AttributeError) as e:
            logger.warning(f"Failed to calculate score for {metric_id}: {e}")
            return None

    def score(self, metric_id: str) -> Optional[float]:
        """
        Get cached score for a metric.

        Args:
            metric_id: The metric ID to retrieve score for

        Returns:
            Cached score from 0.0 (worst) to 1.0 (best), or None if not available
        """
        return self._metric_scores.get(metric_id)

    def get_all_scores(self) -> Dict[str, Optional[float]]:
        """
        Get all cached metric scores.

        Returns:
            Dictionary mapping metric IDs to their scores
        """
        return self._metric_scores.copy()

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

    def apply_policies(self) -> Dict[str, Any]:
        """
        Apply all enabled policies and return aggregated effects.

        Each policy's apply() method is called in registration order.
        If a policy raises an exception, it's caught and recorded in the effects.

        Returns:
            Dictionary of effects from all applied policies, keyed by policy ID
        """
        # Update all scores before applying policies
        self.update_scores()
        effects: Dict[str, Any] = {}

        for policy in self._policies:
            # Skip disabled policies
            if not getattr(policy, "enabled", False):
                continue

            try:
                result = policy.apply(self)
                if isinstance(result, dict):
                    effects.update(result)
            except Exception as e:
                # Record error but continue processing other policies
                policy_id = getattr(policy, "id", "unknown")
                effects[policy_id] = {"error": str(e)}

        return effects
