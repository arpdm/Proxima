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

from mesa import Model
from proxima_model.sphere_engine.energy_sector import EnergySector
from proxima_model.sphere_engine.science_sector import ScienceSector
from proxima_model.sphere_engine.manufacturing_sector import ManufacturingSector
from proxima_model.policy_engine.policy_engine import PolicyEngine


class WorldSystem(Model):
    def __init__(self, config, seed=None):
        super().__init__(seed=seed)
        self.config = config
        self.running = True

        self.sectors = {}
        self._initialize_sectors()

        goals_config = self.config.get("goals", {})
        self.active_goals = goals_config.get("active_goals", [])
        self.performance_goals = goals_config.get("performance_goals", [])

        # Metrics are now a flat list on config
        self.metric_definitions = self.config.get("metrics", [])
        # Runtime metric state - store as direct float values
        self.performance_metrics = {
            mdef.get("id"): 0.0 for mdef in self.metric_definitions if isinstance(mdef, dict) and mdef.get("id")
        }

        # Environment dynamics
        self.dust_decay_per_step = float(self.config.get("dust_decay_per_step", 0.0))
        # Policy engine (centralizes scoring + throttling)
        self.policy = PolicyEngine(self)

    def _initialize_sectors(self):
        """Initialize all sectors dynamically based on configuration."""
        agents_config = self.config.get("agents_config", {})

        # Initialize each sector based on their specific constructor requirements
        if "energy" in agents_config:
            self.sectors["energy"] = EnergySector(self, agents_config["energy"])

        if "science" in agents_config:
            self.sectors["science"] = ScienceSector(agents_config["science"])

        if "manufacturing" in agents_config:
            self.sectors["manufacturing"] = ManufacturingSector(self, agents_config["manufacturing"])

    def _calculate_sector_allocations(self, available_power):
        """
        Calculate power and priority allocations based on loaded goals configuration.

        Returns:
            tuple: (sector_power_allocations_dict, sector_priorities_dict)
        """
        # Get all operational sectors (excluding energy)
        operational_sectors = {
            name: sector
            for name, sector in self.sectors.items()
            if name != "energy" and hasattr(sector, "get_power_demand")
        }

        # Initialize tracking dictionaries
        sector_power_weights = {name: 0.0 for name in operational_sectors}
        sector_priorities = {name: {} for name in operational_sectors}

        # Process each active goal to build weights and priorities
        for goal in self.active_goals:
            goal_weight = goal.get("priority_weight", 0.0)
            sector_weights = goal.get("sector_weights", {})

            for sector_name, sector_config in sector_weights.items():
                if sector_name not in operational_sectors:
                    continue  # Skip unknown sectors

                if isinstance(sector_config, dict):
                    # Accumulate power allocation weights
                    power_alloc = sector_config.get("power_allocation", 0.0)
                    sector_power_weights[sector_name] += goal_weight * power_alloc

                    # Build task priorities for this sector
                    for task, task_weight in sector_config.items():
                        if task != "power_allocation":
                            current_priority = sector_priorities[sector_name].get(task, 0.0)
                            sector_priorities[sector_name][task] = current_priority + (goal_weight * task_weight)

        # Calculate power demands and allocations
        sector_demands = {name: sector.get_power_demand() for name, sector in operational_sectors.items()}
        total_demand = sum(sector_demands.values())

        if total_demand <= available_power:
            # Sufficient power - give each sector what it needs
            return sector_demands, sector_priorities

        # Insufficient power - allocate proportionally based on goal weights
        total_weight = sum(sector_power_weights.values())
        if total_weight == 0:
            # No goal weights - distribute equally
            equal_share = available_power / len(operational_sectors) if operational_sectors else 0
            sector_allocated = {name: min(demand, equal_share) for name, demand in sector_demands.items()}
        else:
            # Distribute based on normalized goal weights
            sector_allocated = {}
            for sector_name, demand in sector_demands.items():
                weight_ratio = sector_power_weights[sector_name] / total_weight
                allocated = min(demand, available_power * weight_ratio)
                sector_allocated[sector_name] = allocated

        return sector_allocated, sector_priorities

    def step(self):
        """Execute a single simulation step with dynamic sector handling."""
        self.policy.apply_policies()

        # Get operational sectors and calculate total power demand
        operational_sectors = {name: sector for name, sector in self.sectors.items() if name != "energy"}
        total_power_demand = sum(sector.get_power_demand() for sector in operational_sectors.values())

        # Generate available power
        energy_sector = self.sectors.get("energy")
        available_power = energy_sector.step(total_power_demand) if energy_sector else 0

        # Allocate power and priorities to sectors
        sector_allocated, sector_priorities = self._calculate_sector_allocations(available_power)

        # Execute each sector with allocated resources
        for sector_name, sector in operational_sectors.items():
            allocated_power = sector_allocated.get(sector_name, 0)
            priorities = sector_priorities.get(sector_name, {})

            if hasattr(sector, "set_priorities") and priorities:
                sector.set_priorities(priorities)
            sector.step(allocated_power)

        self._update_environment_dynamics()
        self._collect_metrics()

    def get_performance_metric(self, metric_id: str) -> float:
        """Get the current value of a performance metric."""
        return float(self.performance_metrics.get(metric_id, 0.0))

    def set_performance_metric(self, metric_id: str, value: float) -> None:
        """Set the value of a performance metric."""
        self.performance_metrics[metric_id] = float(value)

    def _update_environment_dynamics(self):
        """Apply per-step environment effects like dust decay."""
        if self.dust_decay_per_step > 0:
            current_dust = self.get_performance_metric("IND-DUST-COV")
            self.set_performance_metric("IND-DUST-COV", max(0.0, current_dust - self.dust_decay_per_step))

    def _build_metric_scores(self, selected_ids=None):
        """
        Build a unified score report for metrics (environment + goal-linked).
        """

        # Map definitions by id
        defs_by_id = {m.get("id"): m for m in self.metric_definitions if isinstance(m, dict) and m.get("id")}

        # Map goals by metric id
        goals_by_metric = {}
        for pg in self.performance_goals:
            mid = pg.get("metric_id")
            if mid:
                goals_by_metric[mid] = pg

        # Union of IDs from env defs and performance goals
        ids = set(defs_by_id.keys()) | set(goals_by_metric.keys())
        if selected_ids:
            ids = ids & set(selected_ids)

        report = {}
        for metric_id in ids:
            mdef = defs_by_id.get(metric_id, {})
            current = float(self.performance_metrics.get(metric_id, 0.0))
            low = float(mdef.get("threshold_low", 0.0)) if mdef else 0.0
            high = float(mdef.get("threshold_high", 1.0)) if mdef else 1.0
            mtype = mdef.get("type", "positive") if mdef else "positive"
            score = self.policy.score(metric_id)  # centralized scoring
            status = "within" if mdef and (low <= current <= high) else "unknown" if not mdef else "outside"

            entry = {
                "name": mdef.get("name", metric_id) if mdef else metric_id,
                "unit": mdef.get("unit"),
                "type": mtype,
                "threshold_low": low,
                "threshold_high": high,
                "current": current,
                "status": status,
                "score": score,
            }

            # Attach goal info if this metric is linked to a performance goal
            if metric_id in goals_by_metric:
                pg = goals_by_metric[metric_id]
                entry["goal"] = {
                    "target": float(pg.get("target_value", 0.0)),
                    "direction": pg.get("direction", "minimize"),
                    "weight": float(pg.get("weight", 1.0)),
                    "goal_id": pg.get("goal_id"),
                    "name": pg.get("name"),
                }

            report[metric_id] = dict(entry)

        return report

    def _apply_metric_contributions(self, contributions: dict):
        """Apply aggregated per-step metric deltas from sectors."""
        for metric_id, delta in contributions.items():
            cur = self.get_performance_metric(metric_id)
            new_val = cur + float(delta)
            self.set_performance_metric(metric_id, new_val)

    def _collect_metrics(self):
        """Collect metrics from all sectors dynamically."""
        self.model_metrics = {"environment": {"step": self.steps}}

        # 1) Gather sector metrics and accumulate metric contributions
        aggregated_contrib = {}
        for sector_name, sector in self.sectors.items():
            if hasattr(sector, "get_metrics"):
                m = sector.get_metrics()
                self.model_metrics[sector_name] = m
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
