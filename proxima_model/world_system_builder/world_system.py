"""
world_system.py

PROXIMA LUNAR SIMULATION - WORLD SYSTEM ORCHESTRATOR
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, Any, Optional, Set, List
import logging

from mesa import Model
from proxima_model.sphere_engine.energy_sector import EnergySector
from proxima_model.sphere_engine.science_sector import ScienceSector
from proxima_model.sphere_engine.manufacturing_sector import ManufacturingSector
from proxima_model.sphere_engine.equipment_manufacturing_sector import EquipmentManSector
from proxima_model.sphere_engine.transportation_sector import TransportationSector
from proxima_model.policy_engine.policy_engine import PolicyEngine
from proxima_model.policy_engine.metrics import (
    MetricDefinition,
    MetricScore,
    MetricStatus,
    PerformanceGoal,
)
from proxima_model.event_engine.event_bus import EventBus

logger = logging.getLogger(__name__)


class AllocationMode(Enum):
    """Power allocation strategies."""

    PROPORTIONAL = "proportional"
    EQUAL = "equal"


class WorldSystem(Model):
    """Central orchestrator for the Proxima lunar base simulation."""

    # Sector registry for dynamic initialization
    SECTOR_REGISTRY = {
        "energy": EnergySector,
        "science": ScienceSector,
        "manufacturing": ManufacturingSector,
        "equipment_manufacturing": EquipmentManSector,
        "transportation": TransportationSector,
    }

    def __init__(self, config: Dict[str, Any], seed: Optional[int] = None):
        """
        Initialize world system with configuration.

        Args:
            config: World system configuration dictionary
            seed: Random seed for Mesa model
        """
        super().__init__(seed=seed)

        self.config = config
        self.running = True

        # Power allocation mode (TODO: Move to policy)
        allocation_mode_str = (self.config.get("allocation_mode") or "proportional").lower()
        self.allocation_mode = AllocationMode(allocation_mode_str)

        # Initialize event bus and sectors
        self.event_bus = EventBus()
        self.sectors: Dict[str, Any] = {}
        self._initialize_sectors()

        # Load performance goals configuration
        goals_cfg = self.config.get("goals", {}) or {}
        performance_goals_data = goals_cfg.get("performance_goals", []) or []
        self.performance_goals: List[PerformanceGoal] = [
            PerformanceGoal.from_dict(pg) for pg in performance_goals_data if isinstance(pg, dict)
        ]

        # Load metric definitions (for display/reference only, no thresholds)
        metric_defs_data = self.config.get("metrics", [])
        self._metric_definitions: Dict[str, MetricDefinition] = {}
        for mdef in metric_defs_data:
            if isinstance(mdef, dict) and mdef.get("id"):
                try:
                    metric = MetricDefinition.from_dict(mdef)
                    self._metric_definitions[metric.id] = metric
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️  Invalid metric definition: {e}")

        # Build goals lookup by metric ID
        self._goals_by_metric: Dict[str, PerformanceGoal] = {
            pg.metric_id: pg for pg in self.performance_goals if pg.metric_id
        }

        # Initialize performance metrics (current values)
        self.performance_metrics: Dict[str, float] = {metric_id: 0.0 for metric_id in self._metric_definitions.keys()}

        # Model-wide metrics collection
        self.model_metrics: Dict[str, Any] = {"environment": {"step": 0}}

        # Environment dynamics
        self.dust_decay_per_step = float(self.config.get("dust_decay_per_step", 0.0))

        # Initialize policy engine (after performance_goals is set)
        self.policy = PolicyEngine(self)

    @property
    def metric_definitions(self) -> list:
        """Get metric definitions as list (backwards compatibility)."""
        return [m.to_dict() for m in self._metric_definitions.values()]

    def _initialize_sectors(self) -> None:
        """Initialize all sectors dynamically based on configuration."""
        agents_config = self.config.get("agents_config", {})

        for name, sector_class in self.SECTOR_REGISTRY.items():
            if name in agents_config:
                try:
                    self.sectors[name] = sector_class(self, agents_config[name], self.event_bus)
                    print(self.sectors[name])
                except Exception as e:
                    logger.error(f"⚠️  Failed to initialize {name} sector: {e}")

    def _get_power_consumers(self) -> Dict[str, Any]:
        """Get sectors that can consume power."""
        return {
            name: sector
            for name, sector in self.sectors.items()
            if name != "energy" and hasattr(sector, "get_power_demand")
        }

    def _allocate_power_fairly(self, available_power: float, operational_sectors: Dict[str, Any]) -> Dict[str, float]:
        """
        Compute fair power allocations for all non-energy sectors.

        Args:
            available_power: Total power available for allocation
            operational_sectors: Dictionary of sectors to allocate power to

        Returns:
            Dictionary of sector names to allocated power amounts
        """
        if not operational_sectors or available_power <= 0:
            return {name: 0.0 for name in operational_sectors}

        # Snapshot demands
        demands: Dict[str, float] = {
            name: max(0.0, float(sector.get_power_demand())) for name, sector in operational_sectors.items()
        }

        total_demand = sum(demands.values())

        if total_demand <= 0.0:
            return {name: 0.0 for name in operational_sectors}

        # Case 1: Sufficient power → satisfy all demands
        if total_demand <= available_power:
            return demands

        # Case 2: Scarcity → fair split based on allocation mode
        if self.allocation_mode == AllocationMode.EQUAL:
            num_sectors = len(operational_sectors)
            per_sector = available_power / num_sectors
            return {name: min(per_sector, demands[name]) for name in operational_sectors}
        else:
            # Proportional by demand (default)
            ratio = available_power / total_demand
            return {name: ratio * demands[name] for name in operational_sectors}

    def step(self) -> None:
        """Execute a single simulation step with dynamic sector handling."""

        # Get power-consuming sectors
        power_consumers = self._get_power_consumers()

        # Calculate total power demand
        total_power_demand = sum(float(s.get_power_demand()) for s in power_consumers.values())

        # Generate available power from energy sector
        energy_sector = self.sectors.get("energy")
        available_power = energy_sector.step(total_power_demand) if energy_sector else 0.0

        # Allocate power fairly among non-energy sectors
        sector_allocations = self._allocate_power_fairly(available_power, power_consumers)

        # Step each sector with its allocation
        for name, sector in power_consumers.items():
            alloc = sector_allocations.get(name, 0.0)
            if hasattr(sector, "step"):
                sector.step(alloc)

        self._collect_metrics()
        self._update_environment_dynamics()
        self.policy.update_scores()
        self.policy.apply_policies()

    def get_performance_metric(self, metric_id: str) -> float:
        """Get the current value of a performance metric."""
        return float(self.performance_metrics.get(metric_id, 0.0))

    def set_performance_metric(self, metric_id: str, value: float) -> None:
        """Set the value of a performance metric."""
        self.performance_metrics[metric_id] = float(value)

    def _update_environment_dynamics(self) -> None:
        """Apply per-step environment effects like dust decay."""
        if self.dust_decay_per_step > 0:
            current_dust = self.get_performance_metric("IND-DUST-COV")
            self.set_performance_metric("IND-DUST-COV", max(0.0, current_dust - self.dust_decay_per_step))

    def _determine_metric_status(self, current: float, goal: Optional[PerformanceGoal]) -> str:
        """
        Determine metric status based on performance goal.

        Args:
            current: Current metric value
            goal: Associated performance goal (if any)

        Returns:
            Status string (within/outside/unknown)
        """
        if not goal:
            return MetricStatus.UNKNOWN.value

        # Status based on goal achievement
        if goal.direction == "minimize":
            return MetricStatus.WITHIN.value if current <= goal.target_value else MetricStatus.OUTSIDE.value
        else:  # maximize
            return MetricStatus.WITHIN.value if current >= goal.target_value else MetricStatus.OUTSIDE.value

    def _build_single_metric_score(self, metric_id: str) -> Dict[str, Any]:
        """Build the score report for a single metric."""
        mdef = self._metric_definitions.get(metric_id)
        goal = self._goals_by_metric.get(metric_id)
        current = self.get_performance_metric(metric_id)

        # Determine status based on goal
        status = self._determine_metric_status(current, goal)

        # Get cached score from policy engine (already calculated this step)
        score_value = self.policy.score(metric_id)

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

    def _build_metric_scores(self, selected_ids: Optional[Set[str]] = None) -> Dict[str, Dict[str, Any]]:
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
        return {metric_id: self._build_single_metric_score(metric_id) for metric_id in ids_to_process}

    def _apply_metric_contributions(self, contributions: Dict[str, float]) -> None:
        """Apply aggregated per-step metric contributions from sectors."""
        for metric_id, delta in contributions.items():
            current_value = self.get_performance_metric(metric_id)
            self.set_performance_metric(metric_id, current_value + float(delta))

    def _collect_metrics(self) -> None:
        """Collect metrics from all sectors dynamically."""
        self.model_metrics = {"environment": {"step": self.steps}}

        # Gather sector metrics and accumulate metric contributions
        aggregated_contrib: Dict[str, float] = {}

        for sector_name, sector in self.sectors.items():
            if not hasattr(sector, "get_metrics"):
                continue

            metrics = sector.get_metrics()
            self.model_metrics[sector_name] = metrics

            # Accumulate contributions
            contributions = (metrics or {}).get("metric_contributions", {})

            if contributions:
                logger.debug(f"🔍 Step {self.steps} - {sector_name}: {contributions}")

            for metric_id, delta in contributions.items():
                aggregated_contrib[metric_id] = aggregated_contrib.get(metric_id, 0.0) + float(delta)

        if aggregated_contrib:
            logger.debug(f"🌪️ Step {self.steps} - Total contributions: {aggregated_contrib}")

        # Apply contributions to performance metrics before scoring
        if aggregated_contrib:
            self._apply_metric_contributions(aggregated_contrib)

        # Build unified score report
        scores = self._build_metric_scores()
        self.model_metrics["performance"] = {
            "metrics": self.performance_metrics,
            "scores": scores,
        }
