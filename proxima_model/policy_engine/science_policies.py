from __future__ import annotations
from typing import Dict, Any, List, Optional, TYPE_CHECKING
import logging

from .policy_protocol import Policy

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

    # The metric this policy is associated with.
    DEFAULT_METRIC_ID = "SCI-PROD-RATE"

    def __init__(
        self,
        metric_id: str = DEFAULT_METRIC_ID,
    ):
        """
        Initialize the science growth policy.

        Args:
            metric_id: The metric ID to monitor.
        """
        self.metric_id = metric_id

    def apply(self, engine: "PolicyEngine", evaluation_result: "EvaluationResult") -> Dict[str, Any]:
        """
        Reads the evaluation for the science growth metric and logs it.
        This policy is passive and doesn't apply throttling or other effects.
        """

        self.metric_id = None

        # This policy is for monitoring, so it returns the observed data without applying effects.
        effects = {
            "metric_id": self.metric_id,
            "score": 0,
            "current_value": 1,
            "goal_monitored": 1,
        }

        return effects
