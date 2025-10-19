"""
manufacturing_sector.py

PROXIMA LUNAR SIMULATION - MANUFACTURING SECTOR MANAGER

PURPOSE:
========
The ManufacturingSector manages all In-Situ Resource Utilization (ISRU) operations on the lunar base.
It orchestrates extraction and generation agents to produce essential resources (He3, metals, water, etc.)
based on dynamic priority systems and available power budgets.

CORE ALGORITHMS:
===============

1) Each managed stock has a target band [min, max] from config (defaults shown).
2) At each step, compute deficiency = max(0, min_target - current_stock).
3) Choose the task whose *primary output stock* has the largest deficiency,
   but only if that task is currently feasible (agents available by type).
4) If no deficiency > 0, set all agents INACTIVE and return unused power.

"""

from __future__ import annotations

from typing import Dict, List, Tuple, Optional, Any
from proxima_model.components.isru import ISRUExtractor, ISRUGenerator


class ManufacturingSector:
    """Manages ISRU operations, resource stocks, and manufacturing processes."""

    # Task → (generator_mode, extractor_mode)
    TASK_TO_MODES: Dict[str, Tuple[Optional[str], Optional[str]]] = {
        "He3": ("HE3", None),
        "Water": (None, "ICE"),
        "Regolith": (None, "REGOLITH"),
    }

    # Task → primary output stock key
    TASK_TO_STOCK: Dict[str, str] = {
        "He3": "He3_kg",
        "Metal": "Metal_kg",
        "Water": "H2O_kg",
        "Regolith": "FeTiO3_kg",
        "Electrolysis": "O2_kg",  # adjust if you track H2 separately or prioritize H2
    }

    def __init__(self, model, config, event_bus):
        """
        Initialize manufacturing sector with agents and resource stocks.

        Args:
            model: Reference to world system model
            config: Manufacturing configuration from database
        """
        self.model = model
        self.config = config
        self.event_bus = event_bus

        self.isru_extractors: List[ISRUExtractor] = []
        self.isru_generators: List[ISRUGenerator] = []
        self.pending_stock_flows: List[Dict[str, Dict[str, float]]] = []

        self.extractor_throttle = 1.0

        # Initialize metric contribution tracking
        self.extractor_metric_contributions = {}
        self.generator_metric_contributions = {}

        # Metrics
        self.total_power_consumed = 0.0
        self.step_power_consumed = 0.0
        self.active_operations = 0
        self.operational_extractors_count = 0
        self.operational_generators_count = 0

        # Sector lifecycle
        self.sector_state = "active"

        # Build agents
        for agent_cfg in self.config.get("isru_extractors", []):
            qty = agent_cfg.get("quantity", 1)
            metric_contribution = agent_cfg.get("metric_contribution")
            merged = agent_cfg.get("config", {})
            for _ in range(qty):
                self.isru_extractors.append(ISRUExtractor(self.model, merged))
                self.extractor_metric_contributions = metric_contribution

        for agent_cfg in self.config.get("isru_generators", []):
            metric_contribution = agent_cfg.get("metric_contribution")
            qty = agent_cfg.get("quantity", 1)
            merged = agent_cfg.get("config", {})
            for _ in range(qty):
                self.isru_generators.append(ISRUGenerator(self.model, merged))
                self.generator_metric_contributions = metric_contribution or {}

        # Stocks
        self.stocks: Dict[str, float] = config.get(
            "initial_stocks",
            {"H2O_kg": 0.0, "FeTiO3_kg": 0.0, "He3_kg": 0.0},
        )

        # Minimal buffer targets (can be overridden via config['buffer_targets'])
        default_targets = {
            "He3_kg": {"min": 20, "max": 300},
            "H2O_kg": {"min": 2.0, "max": 10.0},
            "FeTiO3_kg": {"min": 20.0, "max": 100.0},
        }

        self.buffer_targets: Dict[str, Dict[str, float]] = {**default_targets, **config.get("buffer_targets", {})}
        self.event_bus.subscribe("resource_request", self.fulfill_resource_request)

    def fulfill_resource_request(self, requesting_sector: str, resource: str, amount: float):
        """Checks stock and fulfills a resource request from another sector."""
        if self.stocks.get(resource, 0) >= amount:
            self.stocks[resource] -= amount
            print(f"Fulfilling request. Remaining {resource}: {self.stocks[resource]:.2f} kg.")
            self.event_bus.publish(
                "resource_allocated",
                recipient_sector=requesting_sector,
                resource=resource,
                amount=amount,
            )
        else:
            pass
            # print(f"Could not fulfill request for {resource}: Insufficient stock.")

    def _set_extractor_modes(self, mode):
        """Set all extractors to specified operational mode."""
        for extractor in self.isru_extractors:
            extractor.set_operational_mode(mode)

    def _set_generator_modes(self, mode):
        """Set all generators to specified operational mode."""
        for generator in self.isru_generators:
            generator.set_operational_mode(mode)

    def get_stocks(self):
        """Return current stocks (read-only copy)."""
        return self.stocks.copy()

    def add_stock_flow(
        self,
        source_component: str,
        consumed: Optional[Dict[str, float]] = None,
        generated: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Add a stock flow transaction to pending queue.

        Stock flows are batched and processed atomically to prevent
        race conditions and ensure resource conservation.

        Args:
            source_component: Component generating the flow
            consumed_resources: Resources consumed (optional)
            generated_resources: Resources generated (optional)
        """
        self.pending_stock_flows.append(
            {
                "source": source_component,
                "consumed": consumed or {},
                "generated": generated or {},
            }
        )

    def process_all_stock_flows(self):
        """
        Process all pending stock flows atomically.

        Ensures resource conservation by applying all consumption
        and generation transactions in a single batch operation.

        Returns:
            dict: Summary of total consumed and generated resources
        """
        if not self.pending_stock_flows:
            return {}

        total_consumed = {}
        total_generated = {}

        # Process all flows atomically
        for flow in self.pending_stock_flows:
            # Apply consumption
            for resource, amount in flow["consumed"].items():
                if resource in self.stocks:
                    self.stocks[resource] = max(0, self.stocks[resource] - amount)
                    total_consumed[resource] = total_consumed.get(resource, 0) + amount

            # Apply generation
            for resource, amount in flow["generated"].items():
                self.stocks[resource] = self.stocks.get(resource, 0) + amount
                total_generated[resource] = total_generated.get(resource, 0) + amount

        self.pending_stock_flows = []
        return {"consumed": total_consumed, "generated": total_generated}

    def set_throttle_factor(self, factor: float):
        """WorldSystem hook to throttle ISRU extraction (extractors only)."""
        try:
            self.extractor_throttle = max(0.0, min(1.0, float(factor)))
        except Exception:
            self.extractor_throttle = 1.0

    def get_power_demand(self):
        """
        Calculate total power demand from all ISRU operations.
        Returns zero if sector is inactive to optimize power allocation.
        """
        if self.sector_state == "inactive":
            return 0.0

        # Apply throttle to extractors only
        extractor_demand = sum(agent.get_power_demand() for agent in self.isru_extractors)
        generator_demand = sum(agent.get_power_demand() for agent in self.isru_generators)
        return extractor_demand + generator_demand

    def _assign_agents_to_tasks(self):
        """
        Assign extractors and generators to tasks based on deficiency.
        Agents not assigned to a task are set to INACTIVE.
        """
        # Compute deficiency for each task
        deficiencies = []
        for task, stock_key in self.TASK_TO_STOCK.items():
            tgt = self.buffer_targets.get(stock_key, {"min": 0.0}).get("min", 0.0)
            cur = self.stocks.get(stock_key, 0.0)
            deficiency = max(0.0, float(tgt) - float(cur))
            if deficiency > 0:
                deficiencies.append((task, deficiency))

        # Sort tasks by deficiency (descending)
        sorted_tasks = [t for t, _ in sorted(deficiencies, key=lambda x: -x[1])]

        # Assign extractors
        extractor_modes = []
        for task in sorted_tasks:
            _, e_mode = self.TASK_TO_MODES.get(task, (None, None))
            if e_mode:
                extractor_modes.append(e_mode)
        for i, extractor in enumerate(self.isru_extractors):
            if i < len(extractor_modes):
                extractor.set_operational_mode(extractor_modes[i])
            else:
                # Assign to the most needed task if any exist
                if extractor_modes:
                    extractor.set_operational_mode(extractor_modes[0])  # Most needed task's mode
                else:
                    extractor.set_operational_mode("INACTIVE")

        # Assign generators
        generator_modes = []
        for task in sorted_tasks:
            g_mode, _ = self.TASK_TO_MODES.get(task, (None, None))
            if g_mode:
                generator_modes.append(g_mode)
        for i, generator in enumerate(self.isru_generators):
            if i < len(generator_modes):
                generator.set_operational_mode(generator_modes[i])
            else:
                # Assign to the most needed task if any exist
                if generator_modes:
                    generator.set_operational_mode(generator_modes[0])  # Most needed task's mode
                else:
                    generator.set_operational_mode("INACTIVE")

    def step(self, allocated_power):
        """
        Execute a manufacturing of materials based on bffer-based policy

        EXECUTION SEQUENCE:
        1) If sector is inactive or no power → return power.
        2) Pick a single task by largest stock deficiency.
        3) Apply modes for that task.
        4) Run generators first, then extractors (respect throttle).
        5) Commit stock flows atomically; return unused power.

        Args:
            allocated_power: Power budget allocated by world system

        Returns:
            float: Unused power returned to world system
        """
        # Initialize operational tracking for metrics
        self.operational_extractors_count = 0
        self.operational_generators_count = 0
        self.active_operations = 0
        self.step_power_consumed = 0.0

        if allocated_power <= 0 or self.sector_state == "inactive":
            self._set_all_agents_inactive()
            return allocated_power

        self._assign_agents_to_tasks()

        # Generator-first budgeting
        remaining_power = allocated_power
        total_generator_demand = sum(g.get_power_demand() for g in self.isru_generators)
        generator_budget = min(total_generator_demand, remaining_power)

        # Execute generation operations first (with reserved power)
        for g in self.isru_generators:
            pd = g.get_power_demand()
            if pd > 0 and remaining_power >= pd:
                gen, cons, used = g.generate_resources(pd, self.stocks)
                if gen:
                    self.add_stock_flow("ISRU_Generator", cons, gen)
                self.step_power_consumed += used
                remaining_power -= used
                if used > 0:
                    self.active_operations += 1
                    self.operational_generators_count += 1

        # Execute extraction operations with remaining power
        extractor_used = 0.0
        extractor_cap = max(0, int(len(self.isru_extractors) * self.extractor_throttle))
        for i, ex in enumerate(self.isru_extractors):
            if i >= extractor_cap:
                break
            pd = max(0, ex.get_power_demand())
            if pd <= remaining_power and extractor_used + pd <= (allocated_power - generator_budget):
                gen, used = ex.extract_resources(pd)
                if gen:
                    self.add_stock_flow("ISRU_Extractor", None, gen)
                self.step_power_consumed += used
                remaining_power -= used
                extractor_used += used
                if used > 0:
                    self.active_operations += 1
                    self.operational_extractors_count += 1

        self.process_all_stock_flows()
        self.total_power_consumed += self.step_power_consumed

    def _create_metric_map(self):
        """
        Create a map of metric IDs and their corresponding values.
        Only contributes metrics if agents actually operated in this step.

        Returns:
            dict: A dictionary where keys are metric IDs and values are their contributions.
        """
        metric_map = {}
        value = float(
            self.extractor_metric_contributions.get(
                "value", self.extractor_metric_contributions.get("contribution_value", 0.0)
            )
        )
        metric_map["IND-DUST-COV"] = self.operational_extractors_count * value
        return metric_map

    def get_metrics(self):
        """
        Return comprehensive manufacturing sector metrics including DRR token tracking.

        Returns:
            dict: Manufacturing sector performance metrics
        """
        return {
            "power_demand": self.get_power_demand(),
            "power_consumed": self.step_power_consumed,
            "active_operations": self.active_operations,
            "operational_extractors": getattr(self, "operational_extractors_count", 0),  # Actual operational count
            "operational_generators": getattr(self, "operational_generators_count", 0),  # Actual operational count
            "sector_state": self.sector_state,
            **{f"stock_{k}": v for k, v in self.stocks.items()},
            "metric_contributions": self._create_metric_map(),
        }

    def _set_all_agents_inactive(self) -> None:
        for agent in self.isru_extractors + self.isru_generators:
            if hasattr(agent, "set_agent_state"):
                agent.set_agent_state("inactive")
        # Also set modes to INACTIVE so power_demand=0
        for g in self.isru_generators:
            g.set_operational_mode("INACTIVE")
        for ex in self.isru_extractors:
            ex.set_operational_mode("INACTIVE")

    def set_buffer_targets(self, targets: Dict[str, Dict[str, float]]):
        """Hot-update buffer targets; keys are stock names, values have 'min'/'max'."""
        # TODO: Use dynamic buffer target updates
        self.buffer_targets.update(targets or {})
