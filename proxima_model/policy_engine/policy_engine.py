from typing import Dict, Any, List, Optional, Protocol


class Policy(Protocol):
    """Policy protocol for pluggable policies."""

    id: str
    name: str
    enabled: bool

    def apply(self, engine: "PolicyEngine") -> Dict[str, Any]: ...


class DustCoverageThrottlePolicy:
    """
    Throttle science and manufacturing based on Dust Coverage indicator.
    Keeps operations above a minimum floor to avoid total shutdown.
    """

    id = "PLCY-DUST-THROTTLE"
    name = "Dust Coverage Throttling"
    enabled = True

    def __init__(self, metric_id: str = "IND-DUST-COV", min_throttle: float = 0.2, sectors: Optional[List[str]] = None):
        self.metric_id = metric_id
        self.min_throttle = float(min_throttle)
        self.sectors = sectors or ["science", "manufacturing"]

    def apply(self, engine: "PolicyEngine") -> Dict[str, Any]:
        score = engine.score(self.metric_id)
        throttle = max(self.min_throttle, score)

        effects = {"metric_id": self.metric_id, "score": score, "throttle": throttle, "applied_to": []}

        for sname in self.sectors:
            sector = engine.world.sectors.get(sname)
            if sector and hasattr(sector, "set_throttle_factor"):
                sector.set_throttle_factor(throttle)
                effects["applied_to"].append(sname)

        return {self.id: effects}


class PolicyEngine:
    """Extensible policy engine that centralizes scoring and applies policies."""

    def __init__(self, world):
        self.world = world
        self._policies: List[Policy] = [
            DustCoverageThrottlePolicy(),  # default policy
        ]

    # Scoring utility shared by all policies
    def score(self, metric_id: str) -> float:
        """Return 0..1 score from current metric vs thresholds. 1=good."""
        mdef = next((m for m in self.world.metric_definitions if m.get("id") == metric_id), None)
        if not mdef:
            return 1.0
        cur = float(self.world.get_performance_metric(metric_id))
        mtype = mdef.get("type", "positive")
        low = float(mdef.get("threshold_low", 0.0))
        high = float(mdef.get("threshold_high", 1.0))
        span = high - low if high != low else 1.0
        score = (cur - low) / span if mtype == "positive" else (high - cur) / span
        return max(0.0, min(1.0, score))

    # Policy registry management
    def add_policy(self, policy: Policy) -> None:
        self._policies.append(policy)

    def enable_policy(self, policy_id: str, enabled: bool = True) -> bool:
        for p in self._policies:
            if getattr(p, "id", None) == policy_id:
                p.enabled = enabled
                return True
        return False

    def list_policies(self) -> List[Dict[str, Any]]:
        return [
            {"id": getattr(p, "id", None), "name": getattr(p, "name", None), "enabled": getattr(p, "enabled", False)}
            for p in self._policies
        ]

    # Apply all enabled policies and return aggregated effects
    def apply_policies(self) -> Dict[str, Any]:
        effects: Dict[str, Any] = {}
        for policy in self._policies:
            if getattr(policy, "enabled", False):
                try:
                    res = policy.apply(self)
                    if isinstance(res, dict):
                        effects.update(res)
                except Exception as e:
                    effects[getattr(policy, "id", "unknown")] = {"error": str(e)}
        return effects
