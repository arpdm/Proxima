"""
evaluation_engine.py

PROXIMA LUNAR SIMULATION - EVALUATION ENGINE

PURPOSE:
========
Centralized metric evaluation, scoring, and performance tracking.
Decoupled from WorldSystem for better separation of concerns.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, Set, List
from dataclasses import dataclass
import logging

from proxima_model.policy_engine.metrics import (
    MetricDefinition,
    MetricScore,
    MetricStatus,
    PerformanceGoal,
)

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    """Result of metric evaluation for a simulation step."""

    performance_metrics: Dict[str, float]
    scores: Dict[str, Dict[str, Any]]
    aggregated_contributions: Dict[str, float]


class EvaluationEngine:
    """
    Manages metric evaluation, scoring, and performance tracking.

    Responsibilities:
    - Track current metric values
    - Apply metric contributions from sectors
    - Evaluate metric status against goals
    - Build comprehensive score reports
    """

    def __init__(
        self,
        metric_definitions: List[Dict[str, Any]],
        performance_goals: List[Dict[str, Any]],
    ):
        """
        Initialize evaluation engine.

        Args:
            metric_definitions: List of metric definition dictionaries
            performance_goals: List of performance goal dictionaries
        """
        # Load metric definitions
        self._metric_definitions: Dict[str, MetricDefinition] = {}
        for mdef in metric_definitions:
            if isinstance(mdef, dict) and mdef.get("id"):
                try:
                    metric = MetricDefinition.from_dict(mdef)
                    self._metric_definitions[metric.id] = metric
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️  Invalid metric definition: {e}")

        # Load performance goals
        self.performance_goals: List[PerformanceGoal] = [
            PerformanceGoal.from_dict(pg) for pg in performance_goals if isinstance(pg, dict)
        ]

        # Build goals lookup by metric ID
        self._goals_by_metric: Dict[str, PerformanceGoal] = {
            pg.metric_id: pg for pg in self.performance_goals if pg.metric_id
        }

        # Initialize performance metrics (current values)
        self.performance_metrics: Dict[str, float] = {metric_id: 0.0 for metric_id in self._metric_definitions.keys()}

        logger.info(
            f"✅ Evaluation engine initialized: "
            f"{len(self._metric_definitions)} metrics, "
            f"{len(self.performance_goals)} goals"
        )

    @property
    def metric_definitions(self) -> List[Dict[str, Any]]:
        """Get metric definitions as list (backwards compatibility)."""
        return [m.to_dict() for m in self._metric_definitions.values()]

    def get_performance_metric(self, metric_id: str) -> float:
        """Get the current value of a performance metric."""
        return float(self.performance_metrics.get(metric_id, 0.0))

    def set_performance_metric(self, metric_id: str, value: float) -> None:
        """Set the value of a performance metric."""
        self.performance_metrics[metric_id] = float(value)

    def apply_metric_contributions(self, sector_metrics: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
        """
        Aggregate and apply metric contributions from all sectors.

        Args:
            sector_metrics: Dictionary of sector_name -> sector metrics

        Returns:
            Aggregated contributions by metric_id
        """
        aggregated_contrib: Dict[str, float] = {}

        # Accumulate contributions from all sectors
        for sector_name, metrics in sector_metrics.items():
            if not metrics:
                continue

            contributions = metrics.get("metric_contributions", {})

            if contributions:
                logger.debug(f"🔍 {sector_name}: {contributions}")

            for metric_id, delta in contributions.items():
                aggregated_contrib[metric_id] = aggregated_contrib.get(metric_id, 0.0) + float(delta)

        if aggregated_contrib:
            logger.debug(f"🌪️ Total contributions: {aggregated_contrib}")

        # Apply contributions to performance metrics
        for metric_id, delta in aggregated_contrib.items():
            current_value = self.get_performance_metric(metric_id)
            self.set_performance_metric(metric_id, current_value + delta)

        return aggregated_contrib

    def apply_environment_dynamics(self, dust_decay_per_step: float = 0.0) -> None:
        """
        Apply per-step environment effects like dust decay.

        Args:
            dust_decay_per_step: Amount of dust coverage to decay per step
        """
        if dust_decay_per_step > 0:
            current_dust = self.get_performance_metric("IND-DUST-COV")
            self.set_performance_metric("IND-DUST-COV", max(0.0, current_dust - dust_decay_per_step))

    def calculate_score(self, metric_id: str) -> Optional[float]:
        """
        Calculate normalized score for a metric (0.0 to 1.0).
        
        Uses the actual PerformanceGoal attributes (target_value only).
        
        Args:
            metric_id: ID of the metric to score
        
        Returns:
            Score value between 0.0 and 1.0, or None if no goal defined
        """
        goal = self._goals_by_metric.get(metric_id)
        if not goal:
            return None
        
        current = self.get_performance_metric(metric_id)
        target = goal.target_value
        
        # Simple scoring: 1.0 if target achieved, otherwise proportional
        if goal.direction == "minimize":
            if current <= target:
                return 1.0
            else:
                # Score decreases as we go above target
                # Assume baseline is 2x the target for normalization
                baseline = target * 2.0 if target > 0 else 1.0
                if current >= baseline:
                    return 0.0
                else:
                    return 1.0 - ((current - target) / (baseline - target))
        else:  # maximize
            if current >= target:
                return 1.0
            else:
                # Score increases as we approach target from 0
                if target <= 0:
                    return 0.0
                return current / target
            
    def determine_metric_status(self, metric_id: str) -> str:
        """
        Determine metric status based on performance goal.

        Args:
            metric_id: ID of the metric to evaluate

        Returns:
            Status string (within/outside/unknown)
        """
        goal = self._goals_by_metric.get(metric_id)
        if not goal:
            return MetricStatus.UNKNOWN.value

        current = self.get_performance_metric(metric_id)

        # Status based on goal achievement
        if goal.direction == "minimize":
            return MetricStatus.WITHIN.value if current <= goal.target_value else MetricStatus.OUTSIDE.value
        else:  # maximize
            return MetricStatus.WITHIN.value if current >= goal.target_value else MetricStatus.OUTSIDE.value

    def build_metric_score(self, metric_id: str) -> Dict[str, Any]:
        """
        Build the score report for a single metric.

        Args:
            metric_id: ID of the metric to score

        Returns:
            Dictionary containing metric score information
        """
        mdef = self._metric_definitions.get(metric_id)
        goal = self._goals_by_metric.get(metric_id)
        current = self.get_performance_metric(metric_id)

        # Determine status based on goal
        status = self.determine_metric_status(metric_id)

        # Calculate score
        score_value = self.calculate_score(metric_id)

        # Build score entry
        score = MetricScore(
            name=mdef.name if mdef else metric_id,
            unit=mdef.unit if mdef else None,
            type=mdef.type if mdef else "positive",
            current=current,
            status=status,
            score=score_value,
            goal=goal.to_dict() if goal else None,
        )

        return score.to_dict()

    def build_all_scores(self, selected_ids: Optional[Set[str]] = None) -> Dict[str, Dict[str, Any]]:
        """
        Build a unified score report for metrics.

        Args:
            selected_ids: Optional set of metric IDs to include (None = all)

        Returns:
            Dictionary of metric IDs to score information
        """
        # Union of all known metric IDs
        all_ids = set(self._metric_definitions.keys()) | set(self._goals_by_metric.keys())

        # Filter by selected_ids if provided
        ids_to_process = all_ids & selected_ids if selected_ids else all_ids

        # Build scores for each metric
        return {metric_id: self.build_metric_score(metric_id) for metric_id in ids_to_process}

    def evaluate(self, sector_metrics: Dict[str, Dict[str, Any]], dust_decay_per_step: float = 0.0) -> EvaluationResult:
        """
        Perform complete evaluation for a simulation step.

        Args:
            sector_metrics: Dictionary of sector_name -> sector metrics
            dust_decay_per_step: Environment dust decay rate

        Returns:
            EvaluationResult containing metrics, scores, and contributions
        """
        # Apply metric contributions from sectors
        aggregated_contrib = self.apply_metric_contributions(sector_metrics)

        # Apply environment dynamics
        self.apply_environment_dynamics(dust_decay_per_step)

        # Build comprehensive score report
        scores = self.build_all_scores()

        return EvaluationResult(
            performance_metrics=self.performance_metrics.copy(),
            scores=scores,
            aggregated_contributions=aggregated_contrib,
        )
