"""
world_system.py

PROXIMA LUNAR SIMULATION - WORLD SYSTEM ORCHESTRATOR

PURPOSE:
========
The WorldSystem class serves as the central orchestrator for the Proxima lunar base simulation.
It manages three primary sectors (Energy, Science, Manufacturing) and coordinates resource
allocation based on dynamic goal priorities loaded from the database.

CORE ALGORITHMS:
===============

1. GOAL-DRIVEN RESOURCE ALLOCATION:
   - Loads active goals from database configuration
   - Each goal defines sector weights and power allocation ratios
   - Calculates weighted priorities across all active goals
   - Dynamically allocates power based on goal importance

2. POWER DISTRIBUTION ALGORITHM:
   - Step 1: Calculate total power demand from all sectors
   - Step 2: Generate available power through energy sector
   - Step 3: Apply goal-based allocation ratios to distribute power
   - Step 4: Execute sectors with allocated power budgets

3. MANUFACTURING TASK PRIORITIZATION:
   - Extracts task weights from goal configurations
   - Builds dynamic priority matrix for manufacturing operations
   - Supports: He3, Metal, Water, Regolith, Electrolysis tasks
   - Uses Deficit Round Robin (DRR) scheduling in manufacturing sector

OPERATION FLOW:
==============
Init Phase:
- Load goal configurations from database via world system builder
- Initialize three sectors with their respective agent configurations
- Set up metrics collection framework

Simulation Step:
1. Query power demands from Science and Manufacturing sectors
2. Run Energy sector to generate available power
3. Calculate goal-weighted allocation ratios
4. Distribute power to sectors based on active goal priorities
5. Execute each sector with allocated power budget
6. Collect and aggregate performance metrics
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Any, Optional, Set

from mesa import Model
from proxima_model.sphere_engine.energy_sector import EnergySector
from proxima_model.sphere_engine.science_sector import ScienceSector
from proxima_model.sphere_engine.manufacturing_sector import ManufacturingSector
from proxima_model.sphere_engine.equipment_manufacturing_sector import EquipmentManSector
from proxima_model.sphere_engine.transportation_sector import TransportationSector
from proxima_model.policy_engine.policy_engine import PolicyEngine
from proxima_model.event_engine.event_bus import EventBus


class AllocationMode(Enum):
    """Power allocation strategies."""

    PROPORTIONAL = "proportional"
    EQUAL = "equal"


class MetricStatus(Enum):
    """Metric threshold status."""

    WITHIN = "within"
    OUTSIDE = "outside"
    UNKNOWN = "unknown"


class GoalDirection(Enum):
    """Goal optimization direction."""

    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


@dataclass
class MetricDefinition:
    """Definition of a performance metric."""

    id: str
    name: str
    unit: Optional[str] = None
    type: str = "positive"
    threshold_low: float = 0.0
    threshold_high: float = 1.0

    def __post_init__(self):
        """Validate metric definition."""
        if self.threshold_low > self.threshold_high:
            raise ValueError("threshold_low cannot exceed threshold_high")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricDefinition":
        """Create from dictionary."""
        return cls(
            id=data.get("id"),
            name=data.get("name", data.get("id")),
            unit=data.get("unit"),
            type=data.get("type", "positive"),
            threshold_low=float(data.get("threshold_low", 0.0)),
            threshold_high=float(data.get("threshold_high", 1.0)),
        )


@dataclass
class PerformanceGoal:
    """Performance goal configuration."""

    goal_id: str
    name: str
    metric_id: str
    target_value: float
    direction: str = "minimize"
    weight: float = 1.0

    def __post_init__(self):
        """Validate goal configuration."""
        if self.weight < 0:
            raise ValueError("Weight must be non-negative")
        if self.direction not in [GoalDirection.MINIMIZE.value, GoalDirection.MAXIMIZE.value]:
            raise ValueError(f"Invalid direction: {self.direction}")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceGoal":
        """Create from dictionary."""
        return cls(
            goal_id=data.get("goal_id"),
            name=data.get("name", "Unknown Goal"),
            metric_id=data.get("metric_id"),
            target_value=float(data.get("target_value", 0.0)),
            direction=data.get("direction", "minimize"),
            weight=float(data.get("weight", 1.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "goal_id": self.goal_id,
            "name": self.name,
            "target": self.target_value,
            "direction": self.direction,
            "weight": self.weight,
        }


@dataclass
class MetricScore:
    """Score report for a single metric."""

    name: str
    unit: Optional[str]
    type: str
    threshold_low: float
    threshold_high: float
    current: float
    status: str
    score: float
    goal: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        data = {
            "name": self.name,
            "unit": self.unit,
            "type": self.type,
            "threshold_low": self.threshold_low,
            "threshold_high": self.threshold_high,
            "current": self.current,
            "status": self.status,
            "score": self.score,
        }
        if self.goal:
            data["goal"] = self.goal
        return data


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

        # Load goals configuration
        goals_cfg = self.config.get("goals", {}) or {}
        performance_goals_data = goals_cfg.get("performance_goals", []) or []
        self.performance_goals = [
            PerformanceGoal.from_dict(pg) for pg in performance_goals_data if isinstance(pg, dict)
        ]

        # Load metrics configuration
        metric_defs_data = self.config.get("metrics", [])
        self._metric_definitions: Dict[str, MetricDefinition] = {}
        for mdef in metric_defs_data:
            if isinstance(mdef, dict) and mdef.get("id"):
                try:
                    metric = MetricDefinition.from_dict(mdef)
                    self._metric_definitions[metric.id] = metric
                except (ValueError, TypeError) as e:
                    print(f"⚠️  Invalid metric definition: {e}")

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

        # Initialize policy engine
        self.policy = PolicyEngine(self)

    @property
    def metric_definitions(self) -> list:
        """Get metric definitions as list (backwards compatibility)."""
        return [
            {
                "id": m.id,
                "name": m.name,
                "unit": m.unit,
                "type": m.type,
                "threshold_low": m.threshold_low,
                "threshold_high": m.threshold_high,
            }
            for m in self._metric_definitions.values()
        ]

    def _initialize_sectors(self) -> None:
        """Initialize all sectors dynamically based on configuration."""
        agents_config = self.config.get("agents_config", {})

        for name, sector_class in self.SECTOR_REGISTRY.items():
            if name in agents_config:
                try:
                    self.sectors[name] = sector_class(self, agents_config[name], self.event_bus)
                except Exception as e:
                    print(f"⚠️  Failed to initialize {name} sector: {e}")

    def _get_power_consumers(self) -> Dict[str, Any]:
        """Get sectors that can consume power (cached for performance)."""
        return {
            name: sector
            for name, sector in self.sectors.items()
            if name != "energy" and hasattr(sector, "get_power_demand")
        }

    def _allocate_power_fairly(self, available_power: float, operational_sectors: Dict[str, Any]) -> Dict[str, float]:
        """
        Compute fair power allocations for all non-energy sectors.

        Policy:
          - If Σ demand ≤ available_power, allocate each demand exactly.
          - Else, allocate proportionally to demand (or equally if equal mode).

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

        # If nobody needs power, allocate zeros
        if total_demand <= 0.0:
            return {name: 0.0 for name in operational_sectors}

        # Case 1: Sufficient power → satisfy all demands
        if total_demand <= available_power:
            return demands

        # Case 2: Scarcity → fair split based on allocation mode
        # TODO: This will be changed based on policy
        if self.allocation_mode == AllocationMode.EQUAL:
            # Equal-share baseline, capped by demand
            num_sectors = len(operational_sectors)
            per_sector = available_power / num_sectors
            return {name: min(per_sector, demands[name]) for name in operational_sectors}
        else:
            # Proportional by demand (default)
            ratio = available_power / total_demand  # < 1.0 in scarcity
            return {name: ratio * demands[name] for name in operational_sectors}

    def step(self) -> None:
        """Execute a single simulation step with dynamic sector handling."""
        # Allow policy engine to apply any external constraints (e.g., throttles)
        self.policy.apply_policies()

        # Get power-consuming sectors (do this once per step)
        power_consumers = self._get_power_consumers()

        # Calculate total power demand
        total_power_demand = sum(float(s.get_power_demand()) for s in power_consumers.values())

        # Generate available power from energy sector (if present)
        energy_sector = self.sectors.get("energy")
        available_power = energy_sector.step(total_power_demand) if energy_sector else 0.0

        # Allocate power fairly among non-energy sectors
        sector_allocations = self._allocate_power_fairly(available_power, power_consumers)

        # Step each sector with its allocation
        for name, sector in power_consumers.items():
            alloc = sector_allocations.get(name, 0.0)
            if hasattr(sector, "step"):
                sector.step(alloc)

        # Update environment and collect metrics
        self._update_environment_dynamics()
        self._collect_metrics()

    # ---------------------------------------------------------------------
    # Metrics & environment
    # ---------------------------------------------------------------------

    def get_performance_metric(self, metric_id: str) -> float:
        """
        Get the current value of a performance metric.

        Args:
            metric_id: Metric identifier

        Returns:
            Current metric value (0.0 if not found)
        """
        return float(self.performance_metrics.get(metric_id, 0.0))

    def set_performance_metric(self, metric_id: str, value: float) -> None:
        """
        Set the value of a performance metric.

        Args:
            metric_id: Metric identifier
            value: New metric value
        """
        self.performance_metrics[metric_id] = float(value)

    def _update_environment_dynamics(self) -> None:
        """
        Apply per-step environment effects like dust decay.

        Environmental impacts may dissipate over time, so this runs at every step
        to update performance metrics after operations.
        """
        if self.dust_decay_per_step > 0:
            current_dust = self.get_performance_metric("IND-DUST-COV")
            self.set_performance_metric("IND-DUST-COV", max(0.0, current_dust - self.dust_decay_per_step))

    def _determine_metric_status(self, current: float, low: float, high: float, has_definition: bool) -> str:
        """
        Determine metric status based on thresholds.

        Args:
            current: Current metric value
            low: Lower threshold
            high: Upper threshold
            has_definition: Whether metric definition exists

        Returns:
            Status string (within/outside/unknown)
        """
        if not has_definition:
            return MetricStatus.UNKNOWN.value
        return MetricStatus.WITHIN.value if low <= current <= high else MetricStatus.OUTSIDE.value

    def _build_single_metric_score(self, metric_id: str) -> Dict[str, Any]:
        """
        Build the score report for a single metric.

        Args:
            metric_id: Metric identifier

        Returns:
            Dictionary containing metric score information
        """
        mdef = self._metric_definitions.get(metric_id)
        current = self.get_performance_metric(metric_id)

        # Use metric definition values or defaults
        if mdef:
            low = mdef.threshold_low
            high = mdef.threshold_high
            name = mdef.name
            unit = mdef.unit
            metric_type = mdef.type
        else:
            low = 0.0
            high = 1.0
            name = metric_id
            unit = None
            metric_type = "positive"

        # Determine status
        status = self._determine_metric_status(current, low, high, mdef is not None)

        # Build score entry
        score = MetricScore(
            name=name,
            unit=unit,
            type=metric_type,
            threshold_low=low,
            threshold_high=high,
            current=current,
            status=status,
            score=self.policy.score(metric_id),
        )

        # Attach performance goal info if present for this metric
        if metric_id in self._goals_by_metric:
            pg = self._goals_by_metric[metric_id]
            score.goal = pg.to_dict()

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
        """
        Apply aggregated per-step metric contributions from sectors.

        Args:
            contributions: Dictionary of metric IDs to delta values
        """
        for metric_id, delta in contributions.items():
            current_value = self.get_performance_metric(metric_id)
            self.set_performance_metric(metric_id, current_value + float(delta))

    def _collect_metrics(self) -> None:
        """Collect metrics from all sectors dynamically."""
        self.model_metrics = {"environment": {"step": self.steps}}

        # 1) Gather sector metrics and accumulate metric contributions
        aggregated_contrib: Dict[str, float] = {}

        for sector_name, sector in self.sectors.items():
            if not hasattr(sector, "get_metrics"):
                continue

            metrics = sector.get_metrics()
            self.model_metrics[sector_name] = metrics

            # Accumulate contributions
            contributions = (metrics or {}).get("metric_contributions", {})
            for metric_id, delta in contributions.items():
                aggregated_contrib[metric_id] = aggregated_contrib.get(metric_id, 0.0) + float(delta)

        # 2) Apply contributions to performance metrics before scoring
        if aggregated_contrib:
            self._apply_metric_contributions(aggregated_contrib)

        # 3) Build unified score report
        scores = self._build_metric_scores()
        self.model_metrics["performance"] = {
            "metrics": self.performance_metrics,  # Direct dict of metric_id: float_value
            "scores": scores,
        }
