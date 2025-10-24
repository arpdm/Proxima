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
from enum import Enum, auto
from typing import Dict, Any, List, Optional, Protocol


class MetricType(Enum):
    """Type of metric for scoring normalization."""

    POSITIVE = "positive"  # Higher values are better
    NEGATIVE = "negative"  # Lower values are better


class PolicyStatus(Enum):
    """Status of a policy."""

    ENABLED = auto()
    DISABLED = auto()


@dataclass
class MetricDefinition:
    """Definition of a performance metric."""

    id: str
    name: str
    type: MetricType = MetricType.POSITIVE
    threshold_low: float = 0.0
    threshold_high: float = 1.0

    def __post_init__(self):
        """Validate metric definition."""
        if self.threshold_low > self.threshold_high:
            raise ValueError("threshold_low cannot exceed threshold_high")


@dataclass
class PolicyEffect:
    """Result of applying a policy."""

    policy_id: str
    metric_id: Optional[str] = None
    score: Optional[float] = None
    throttle: Optional[bool] = None
    applied_to: List[str] = field(default_factory=list)
    error: Optional[str] = None


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


class DustCoverageThrottlePolicy:
    """
    Policy: Dust Coverage Throttling

    Dynamically throttles activity in specified sectors (default: science and manufacturing)
    based on the current Dust Coverage metric. This policy prevents total shutdown by enforcing
    a minimum throttle floor, ensuring that operations continue at a reduced rate even under
    adverse environmental conditions.

    The throttling is probability based: This creates a probabilisting throttling where if
    thottling factor is lets say 20%, 20% of steps are used to pause operations.

    Attributes
    ----------
    id : str
        Unique policy identifier
    name : str
        Human-readable policy name
    enabled : bool
        Whether the policy is active
    metric_id : str
        The metric ID to monitor for dust coverage
    sectors : List[str]
        List of sector names to apply throttling to

    Notes
    -----
    - Sectors must implement a `set_throttle_factor(throttle:float)` method for throttling to take effect.
    - The policy is robust to metric fluctuations and avoids complete operational shutdowns
      by maintaining a baseline level of activity.
    """

    id = "PLCY-DUST-THROTTLE"
    name = "Dust Coverage Throttling"
    enabled = True

    # Default configuration
    DEFAULT_METRIC_ID = "IND-DUST-COV"
    DEFAULT_SECTORS = ["science", "manufacturing"]

    def __init__(
        self,
        metric_id: str = DEFAULT_METRIC_ID,
        sectors: Optional[List[str]] = None,
    ):
        """
        Initialize dust coverage throttle policy.

        Args:
            metric_id: The metric ID to monitor (default: "IND-DUST-COV")
            sectors: Sectors to throttle (default: ["science", "manufacturing"])
        """
        self.metric_id = metric_id
        self.sectors = sectors if sectors is not None else self.DEFAULT_SECTORS.copy()

    def apply(self, engine: "PolicyEngine") -> Dict[str, Any]:
        """
        Apply dust coverage throttling policy.

        Args:
            engine: The policy engine instance

        Returns:
            Dictionary containing policy effects
        """

        score = engine.score(self.metric_id)
        throttle = abs(1 - score) * 0.75

        effects = PolicyEffect(
            policy_id=self.id, metric_id=self.metric_id, score=score, throttle=throttle, applied_to=[]
        )

        # Apply throttle to each configured sector
        for sector_name in self.sectors:
            sector = engine.world.sectors.get(sector_name)
            if sector and hasattr(sector, "set_throttle_factor"):
                sector.set_throttle_factor(throttle)
                effects.applied_to.append(sector_name)

        return {
            self.id: {
                "metric_id": effects.metric_id,
                "score": effects.score,
                "throttle": effects.throttle,
                "applied_to": effects.applied_to,
            }
        }


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

    def _get_metric_definition(self, metric_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metric definition.

        Args:
            metric_id: The metric ID to retrieve

        Returns:
            Metric definition dictionary or None if not found
        """
        return next((m for m in self.world.metric_definitions if m.get("id") == metric_id), None)

    def score(self, metric_id: str) -> float:
        """
        Return a normalized score (0..1) for the given metric.

        Score Interpretation:
        - 1.0 = optimal/best performance
        - 0.0 = worst performance
        - Based on metric type (positive/negative) and defined thresholds

        Args:
            metric_id: The metric ID to score

        Returns:
            Normalized score between 0.0 and 1.0
        """
        mdef = self._get_metric_definition(metric_id)
        if not mdef:
            return 1.0  # Default to optimal if metric not found

        # Get current value and metric properties
        current_value = float(self.world.get_performance_metric(metric_id))
        metric_type = mdef.get("type", MetricType.POSITIVE.value)
        threshold_low = float(mdef.get("threshold_low", 0.0))
        threshold_high = float(mdef.get("threshold_high", 1.0))

        # Calculate normalized score
        threshold_span = threshold_high - threshold_low if threshold_high != threshold_low else 1.0

        if metric_type == MetricType.POSITIVE.value:
            # Higher values are better
            score = (current_value - threshold_low) / threshold_span
        else:
            # Lower values are better (negative metric)
            score = (threshold_high - current_value) / threshold_span

        # Clamp to valid range
        return max(0.0, min(1.0, score))

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

    def clear_metric_cache(self):
        """Clear the metric definition cache (no longer needed)."""
        pass  # Cache removed, method kept for API compatibility
