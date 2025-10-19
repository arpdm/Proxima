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
from typing import Dict, Tuple

from mesa import Model
from proxima_model.sphere_engine.energy_sector import EnergySector
from proxima_model.sphere_engine.science_sector import ScienceSector
from proxima_model.sphere_engine.manufacturing_sector import ManufacturingSector
from proxima_model.sphere_engine.equipment_manufacturing_sector import EquipmentManSector
from proxima_model.sphere_engine.transportation_sector import TransportationSector
from proxima_model.policy_engine.policy_engine import PolicyEngine
from proxima_model.event_engine.event_bus import EventBus


class WorldSystem(Model):
    def __init__(self, config, seed=None):
        super().__init__(seed=seed)

        self.config = config
        self.running = True

        # Optional allocation mode: "proportional" (default) or "equal"
        # TODO: This needs to be turned into a policy later on. We dont have power allocation mode added to configuration file yet.
        self.allocation_mode = (self.config.get("allocation_mode") or "proportional").lower()

        # Initialize sectors of the world system
        self.sectors: Dict[str, object] = {}
        self.event_bus = EventBus()
        self._initialize_sectors()

        # Get Performance Goals - Defines the goals of the system
        goals_cfg = self.config.get("goals", {}) or {}
        self.performance_goals = goals_cfg.get("performance_goals", []) or []

        # Metrics configuration
        self.metric_definitions = self.config.get("metrics", [])

        # Stores the static definition of each metric. This is for looking up properties like
        self._metric_definitions = {
            m.get("id"): m for m in self.metric_definitions if isinstance(m, dict) and m.get("id")
        }

        # Stores the static goal information associated with a metric.
        self._goals_by_metric = {pg.get("metric_id"): pg for pg in self.performance_goals if pg.get("metric_id")}

        # Stores the current value of each metric. This is the dynamic state that changes every step.
        self.performance_metrics = {
            mdef.get("id"): 0.0 for mdef in self.metric_definitions if isinstance(mdef, dict) and mdef.get("id")
        }

        self.model_metrics = {"environment": {"step": 0}}

        # Environment dynamics
        self.dust_decay_per_step = float(self.config.get("dust_decay_per_step", 0.0))

        # Manages world system policies
        self.policy = PolicyEngine(self)

    def _initialize_sectors(self):
        """Initialize all sectors dynamically based on configuration."""
        agents_config = self.config.get("agents_config", {})

        # Map sector names to their corresponding classes
        sector_map = {
            "energy": EnergySector,
            "science": ScienceSector,
            "manufacturing": ManufacturingSector,
            "equipment_manufacturing": EquipmentManSector,
            "transportation" : TransportationSector
        }

        for name, sector_class in sector_map.items():
            if name in agents_config:
                self.sectors[name] = sector_class(self, agents_config[name], self.event_bus)

    def _allocate_power_fairly(
        self, available_power: float, operational_sectors: Dict[str, object]
    ) -> Dict[str, float]:
        """Compute fair allocations for all non-energy sectors.

        Policy:
          - If Σ demand ≤ available_power, allocate each demand exactly.
          - Else, allocate proportionally to demand.
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

        # Case 2: Scarcity → fair split
        # TODO: This will be changed based on policy
        if self.allocation_mode == "equal":
            # Equal-share baseline, capped by demand
            n = len(operational_sectors)
            per = available_power / n
            return {name: min(per, demands[name]) for name in operational_sectors}
        else:
            # Proportional by demand
            ratio = available_power / total_demand  # < 1.0 here
            return {name: ratio * demands[name] for name in operational_sectors}

    def step(self):
        """Execute a single simulation step with dynamic sector handling."""

        # Allow policy engine to apply any external constraints (e.g., throttles)
        self.policy.apply_policies()

        # Get non-energy sectors that can consume power (do this once)
        power_consumers = {
            name: s for name, s in self.sectors.items() if name != "energy" and hasattr(s, "get_power_demand")
        }

        total_power_demand = sum(float(s.get_power_demand()) for s in power_consumers.values())

        # Generate available power from energy sector (if present)
        energy_sector = self.sectors.get("energy")
        available_power = energy_sector.step(total_power_demand) if energy_sector else 0.0

        # Allocate fairly among non-energy sectors
        sector_allocations = self._allocate_power_fairly(available_power, power_consumers)

        # Step each sector with its allocation
        for name, sector in power_consumers.items():
            alloc = sector_allocations.get(name, 0.0)
            if hasattr(sector, "step"):
                sector.step(alloc)

        self._update_environment_dynamics()
        self._collect_metrics()

    # ---------------------------------------------------------------------
    # Metrics & environment
    # ---------------------------------------------------------------------

    def get_performance_metric(self, metric_id: str) -> float:
        """Get the current value of a performance metric."""
        return float(self.performance_metrics.get(metric_id, 0.0))

    def set_performance_metric(self, metric_id: str, value: float) -> None:
        """Set the value of a performance metric."""
        self.performance_metrics[metric_id] = float(value)

    def _update_environment_dynamics(self):
        """
        Apply per-step environment effects like dust decay. Each human operation causes impact on the environment.
        However, some of those impacts may dessipate over time. As such we run it at every step to update performance
        metrics after each step based on environmental impacts.
        """
        if self.dust_decay_per_step > 0:
            current_dust = self.get_performance_metric("IND-DUST-COV")
            self.set_performance_metric("IND-DUST-COV", max(0.0, current_dust - self.dust_decay_per_step))

    def _build_single_metric_score(self, metric_id: str) -> dict:
        """Build the score report for a single metric."""

        mdef = self._metric_definitions.get(metric_id, {})
        current = self.get_performance_metric(metric_id)
        low = float(mdef.get("threshold_low", 0.0))
        high = float(mdef.get("threshold_high", 1.0))

        # Determine status based on thresholds
        status = "within" if low <= current <= high else "outside"
        if not mdef:
            status = "unknown"

        entry = {
            "name": mdef.get("name", metric_id),
            "unit": mdef.get("unit"),
            "type": mdef.get("type", "positive"),
            "threshold_low": low,
            "threshold_high": high,
            "current": current,
            "status": status,
            "score": self.policy.score(metric_id),
        }

        # Attach performance-goal info if present for this metric
        if metric_id in self._goals_by_metric:
            pg = self._goals_by_metric[metric_id]
            entry["goal"] = {
                "target": float(pg.get("target_value", 0.0)),
                "direction": pg.get("direction", "minimize"),
                "weight": float(pg.get("weight", 1.0)),
                "goal_id": pg.get("goal_id"),
                "name": pg.get("name"),
            }

        return entry

    def _build_metric_scores(self, selected_ids=None):
        """
        Build a unified score report for metrics by iterating through all relevant IDs.
        """
        # Union of all known metric IDs
        all_ids = set(self._metric_definitions.keys()) | set(self._goals_by_metric.keys())

        # Filter by selected_ids if provided
        ids_to_process = all_ids & set(selected_ids) if selected_ids else all_ids

        # Use a dictionary comprehension for a more concise loop
        return {metric_id: self._build_single_metric_score(metric_id) for metric_id in ids_to_process}

    def _apply_metric_contributions(self, contributions: dict):
        """Apply aggregated per-step metric contributiins from sectors."""
        for metric_id, delta in contributions.items():
            cur = self.get_performance_metric(metric_id)
            self.set_performance_metric(metric_id, cur + float(delta))

    def _collect_metrics(self):
        """Collect metrics from all sectors dynamically."""
        self.model_metrics = {"environment": {"step": self.steps}}

        # 1) Gather sector metrics and accumulate metric contributions
        aggregated_contrib = {}
        for sector_name, sector in self.sectors.items():
            if hasattr(sector, "get_metrics"):
                m = sector.get_metrics()
                self.model_metrics[sector_name] = sector.get_metrics()
                contrib = (m or {}).get("metric_contributions", {})
                for metric_id, delta in contrib.items():
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
