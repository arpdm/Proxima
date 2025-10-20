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
from typing import Dict, Any, List, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any as WorldSystem  # Avoid circular import


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
    throttle: Optional[float] = None
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
    min_throttle : float
        The minimum allowed throttle factor (0.0 to 1.0)
    sectors : List[str]
        List of sector names to apply throttling to

    Notes
    -----
    - Sectors must implement a `set_throttle_factor(float)` method for throttling to take effect.
    - The policy is robust to metric fluctuations and avoids complete operational shutdowns
      by maintaining a baseline level of activity.
    - TODO: Throttling policy needs to be adjusted for realism
    - TODO: Performance goal target is not used but should be integrated
    """

    id = "PLCY-DUST-THROTTLE"
    name = "Dust Coverage Throttling"
    enabled = True

    # Default configuration
    DEFAULT_METRIC_ID = "IND-DUST-COV"
    DEFAULT_MIN_THROTTLE = 0.2
    DEFAULT_SECTORS = ["science", "manufacturing"]

    def __init__(
        self,
        metric_id: str = DEFAULT_METRIC_ID,
        min_throttle: float = DEFAULT_MIN_THROTTLE,
        sectors: Optional[List[str]] = None,
    ):
        """
        Initialize dust coverage throttle policy.

        Args:
            metric_id: The metric ID to monitor (default: "IND-DUST-COV")
            min_throttle: Minimum throttle factor (default: 0.2, range: 0.0-1.0)
            sectors: Sectors to throttle (default: ["science", "manufacturing"])
        """
        self.metric_id = metric_id
        self.min_throttle = self._validate_throttle(min_throttle)
        self.sectors = sectors if sectors is not None else self.DEFAULT_SECTORS.copy()

    @staticmethod
    def _validate_throttle(value: float) -> float:
        """Validate throttle value is in valid range."""
        throttle = float(value)
        if not 0.0 <= throttle <= 1.0:
            raise ValueError(f"Throttle must be between 0.0 and 1.0, got {throttle}")
        return throttle

    def apply(self, engine: "PolicyEngine") -> Dict[str, Any]:
        """
        Apply dust coverage throttling policy.

        Args:
            engine: The policy engine instance

        Returns:
            Dictionary containing policy effects
        """
        # TODO: Throttling policy needs to be adjusted for realism
        # TODO: Performance goal target is not used but should be integrated

        score = engine.score(self.metric_id)
        throttle = max(self.min_throttle, score)

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

    The PolicyEngine manages a registry of operational policies, computes normalized scores
    for world system metrics, and applies enabled policies to the simulation world. It supports
    dynamic addition, enabling/disabling, and listing of policies.

    Attributes
    ----------
    world : WorldSystem
        The simulation world object providing metric definitions and sector access
    _policies : List[Policy]
        List of registered policy objects

    Methods
    -------
    score(metric_id: str) -> float
        Returns a normalized score (0..1) for the given metric
    add_policy(policy: Policy) -> None
        Registers a new policy with the engine
    enable_policy(policy_id: str, enabled: bool = True) -> bool
        Enables or disables a policy by its ID
    list_policies() -> List[Dict[str, Any]]
        Returns a summary of all registered policies and their status
    apply_policies() -> Dict[str, Any]
        Applies all enabled policies and returns their aggregated effects
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

        # Cache for metric definitions (optimization)
        self._metric_cache: Dict[str, Dict[str, Any]] = {}

    def _get_metric_definition(self, metric_id: str) -> Optional[Dict[str, Any]]:
        """
        Get metric definition with caching for performance.

        Args:
            metric_id: The metric ID to retrieve

        Returns:
            Metric definition dictionary or None if not found
        """
        if metric_id not in self._metric_cache:
            self._metric_cache[metric_id] = next(
                (m for m in self.world.metric_definitions if m.get("id") == metric_id), None
            )
        return self._metric_cache[metric_id]

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
        """Clear the metric definition cache (useful after metric updates)."""
        self._metric_cache.clear()
