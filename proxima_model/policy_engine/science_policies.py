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
        world_model,
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
        self.growth_duration_t = (
            24 * 180
        ) / world_model.time_scale  # hours * days #TODO: These can be configurable through policy config in database

    def apply(self, engine: "PolicyEngine", evaluation_result: "EvaluationResult") -> Dict[str, Any]:
        """
        Reads the evaluation for the science growth metric and logs it.
        This policy is passive and doesn't apply throttling or other effects.
        """
        
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


class ScienceGrowthUtilizationPolicy(Policy):
    """
    Policy that adjusts science growth rate based on rover utilization.

    If rover utilization is below the threshold, reduces growth rate.
    If utilization is healthy, maintains or increases growth rate.
    """

    id = "PLCY-SCIENCE-UTILIZATION"
    name = "Science Growth Utilization Adjustment"
    enabled = True

    def __init__(
        self,
        world_model,
        utilization_threshold: float = 0.70,
        reduced_growth_rate: float = 0.5,
        normal_growth_rate: float = 2.0,
    ):
        """
        Initialize the utilization-aware growth policy.

        Args:
            utilization_threshold: Minimum operational/total rover ratio (default 70%)
            reduced_growth_rate: Growth rate to apply when utilization is low
            normal_growth_rate: Growth rate to apply when utilization is healthy
        """
        self.utilization_threshold = utilization_threshold
        self.reduced_growth_rate = reduced_growth_rate
        self.normal_growth_rate = normal_growth_rate
        self.sectors = [SectorType.SCIENCE.value]
        self.growth_duration_t = (24 * 180) / world_model.time_scale

    def apply(self, engine: "PolicyEngine", evaluation_result: "EvaluationResult") -> Dict[str, Any]:
        """
        Check rover utilization and adjust growth rate accordingly.
        """

        effects = {
            "policy_id": self.id,
            "applied_to": [],
            "decisions": [],
        }

        for sector_name in self.sectors:
            sector = engine.world.sectors.get(sector_name)
            if not sector:
                continue

            # Get current metrics
            metrics = sector.get_metrics()
            operational = metrics.get("operational_rovers", 0)
            total = metrics.get("total_rovers", 1)
            rovers_needed = metrics.get("rovers_needed_for_growth", 0)

            utilization = operational / total if total > 0 else 0.0

            # Decide on growth rate based on utilization
            if utilization >= self.utilization_threshold:
                target_growth_rate = self.normal_growth_rate
                decision = f"✅ Utilization healthy ({utilization:.1%} >= {self.utilization_threshold:.1%}): maintaining growth rate {self.normal_growth_rate}"
            else:
                target_growth_rate = self.reduced_growth_rate
                decision = (
                    f"⏸️  Low utilization ({utilization:.1%} < {self.utilization_threshold:.1%}): "
                    f"reducing growth rate to {self.reduced_growth_rate} ({rovers_needed} rovers needed, "
                    f"but deferring until utilization improves)"
                )

            effects["decisions"].append(decision)
            logger.info(decision)

            # Apply the adjusted growth rate
            if hasattr(sector, "control_science_growth_rate"):
                sector.control_science_growth_rate(target_growth_rate, self.growth_duration_t)
                effects["applied_to"].append(sector_name)

        return effects
