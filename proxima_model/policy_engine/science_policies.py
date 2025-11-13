from __future__ import annotations
from typing import Dict, Any, List, Optional, TYPE_CHECKING
import logging

from .policy_protocol import Policy
from proxima_model.world_system.world_system_defs import SectorType

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from .policy_engine import PolicyEngine
    from ..world_system.evaluation_engine import EvaluationResult

logger = logging.getLogger(__name__)


class ScienceProductionRate(Policy):
    """
    A policy that monitors the growth of a science-related metric.
    This policy itself doesn't take action, but it serves as a placeholder
    to ensure the goal is evaluated and scored by the EvaluationEngine.
    """

    id = "PLCY-GROWTH-SCIENCE-RATE"
    name = "Science Generation Growth Rate"
    enabled = True

    def __init__(
        self,
        metric_id: str = None,
    ):
        """
        Initialize the science growth policy.

        Args:
            metric_id: The metric ID to monitor.
        """
        self.metric_id = metric_id
        self.sectors = [SectorType.SCIENCE.value]
        self.policy_function = "control_science_growth_rate"
        self.growth_rate = 2
        self.growth_duration_t = 24*60 # hours * days

    def apply(self, engine: "PolicyEngine", evaluation_result: "EvaluationResult") -> Dict[str, Any]:
        """
        Reads the evaluation for the science growth metric and logs it.
        This policy is passive and doesn't apply throttling or other effects.
        """

        # TODO: This policy can be then using other metrics and policies to make better decisions
        # This policy is for monitoring, so it returns the observed data without applying effects.
        effects = {
            "metric_id": self.metric_id,
            "score": 0,
            "current_value": 1,
            "goal_monitored": 1,
            "applied_to": [],
        }

        for sector_name in self.sectors:
            sector = engine.world.sectors.get(sector_name)
            if sector and hasattr(sector, self.policy_function):
                sector.control_science_growth_rate(self.growth_rate, self.growth_duration_t)
                effects["applied_to"].append(sector_name)
                logger.info(f"🔧 Set {sector_name} science growth rate to {self.growth_rate}")
            else:
                logger.warning(f"⚠️ Sector {sector_name} not found or doesn't support science growth rate control")

        return effects
