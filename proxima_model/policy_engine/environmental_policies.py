"""
environmental_policies.py

Contains policies related to environmental conditions.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, TYPE_CHECKING
import logging

from .policy_protocol import Policy

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from .policy_engine import PolicyEngine
    from ..world_system.evaluation_engine import EvaluationResult

logger = logging.getLogger(__name__)


class DustCoverageThrottlePolicy(Policy):
    """Policy that throttles sectors based on dust coverage levels."""

    id = "PLCY-DUST-THROTTLE"
    name = "Dust Coverage Throttling"
    enabled = True

    # CONFIG ================
    DEFAULT_METRIC_ID = "IND-DUST-COV"
    DEFAULT_SECTORS = ["science", "manufacturing"]
    DEFAULT_THROTTLE_FACTOR = 0.8  # Maximum throttle when score = 0
    DEFAULT_THROTTLE_START = 0.7  # Start throttling at 70% of target
    # CONFIG END ==============

    def __init__(
        self,
        metric_id: str = DEFAULT_METRIC_ID,
        sectors: Optional[List[str]] = None,
        throttle_factor: float = DEFAULT_THROTTLE_FACTOR,
        throttle_start_ratio: float = DEFAULT_THROTTLE_START,
    ):
        """
        Initialize dust coverage throttle policy.

        Args:
            metric_id: The metric ID to monitor (default: "IND-DUST-COV")
            sectors: Sectors to throttle (default: ["science", "manufacturing"])
            throttle_factor: Maximum throttle factor when performance is worst (default: 0.8)
            throttle_start_ratio: Ratio of target where throttling begins (default: 0.7)
        """
        self.metric_id = metric_id
        self.sectors = sectors if sectors is not None else self.DEFAULT_SECTORS.copy()
        self.throttle_factor = throttle_factor
        self.throttle_start_ratio = throttle_start_ratio

    def apply(self, engine: "PolicyEngine", evaluation_result: "EvaluationResult") -> Dict[str, Any]:
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
