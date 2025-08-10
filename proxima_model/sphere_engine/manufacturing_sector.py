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

1. DEFICIT ROUND ROBIN (DRR) TASK SCHEDULING:
   - Maintains deficit counters for each manufacturing task
   - Calculates weighted deficits (deficit / priority) for fair scheduling
   - Selects tasks with highest weighted deficit to prevent resource starvation
   - Supports tasks: He3, Metal, Water, Regolith, Electrolysis

2. AGENT STATE MANAGEMENT:
   - Three states: active, inactive, decommissioned
   - Automatic state transitions based on priority levels
   - Power demand returns zero when agents are inactive
   - Prevents unnecessary resource consumption during low-priority periods

3. STOCK FLOW TRANSACTION SYSTEM:
   - Pending stock flows accumulate during operations
   - Atomic processing prevents race conditions
   - Tracks resource consumption and generation separately
   - Maintains resource conservation across all operations

4. OPERATIONAL MODE COORDINATION:
   - Maps manufacturing tasks to agent operational modes
   - Coordinates extractor and generator modes for complex workflows
   - Example: He3 production requires REGOLITH extraction + HE3 generation

OPERATION FLOW:
==============
Initialization:
- Create ISRU agents (extractors/generators) based on configuration
- Initialize resource stocks from database values
- Set up priority system and deficit counters

Priority Update (from World System):
- Receive new task priorities from goal-based allocation
- Update agent states (active/inactive) based on priority levels
- Configure operational modes for selected tasks

Simulation Step:
1. Check sector state - exit early if inactive
2. Run DRR scheduler to select highest-priority task
3. Set all agents to appropriate operational modes
4. Execute extraction operations (if power available)
5. Execute generation operations (if power available)
6. Process all stock flow transactions atomically
7. Update metrics and return unused power
"""

from proxima_model.components.isru import ISRUExtractor, ISRUGenerator


class ManufacturingSector:
    """Manages ISRU operations, resource stocks, and manufacturing processes."""

    def __init__(self, model, config):
        """
        Initialize manufacturing sector with agents and resource stocks.

        Args:
            model: Reference to world system model
            config: Manufacturing configuration from database
        """
        self.model = model
        self.isru_extractors = []
        self.isru_generators = []
        self.config = config

        # Initialize ISRU agents based on configuration
        agents_config = self.config.get("agents_config", [])
        for agent_config in agents_config:
            metric_contribution = agent_config.get("metric_contribution")
            quantity = agent_config.get("quantity", 1)
            subtype = agent_config.get("subtype")
            merged_config = agent_config.get("config")

            # Create agents based on quantity
            for _ in range(quantity):
                if subtype == "extractor":
                    agent = ISRUExtractor(self.model, merged_config)
                    self.extractor_metric_contributions = metric_contribution
                    self.isru_extractors.append(agent)
                elif subtype == "generator":
                    agent = ISRUGenerator(self.model, merged_config)
                    self.generator_metric_contributions = metric_contribution
                    self.isru_generators.append(agent)

        # Resource stocks - loaded from database
        self.stocks = config.get(
            "initial_stocks",
            {
                "H2_kg": 0.0,
                "O2_kg": 0.0,
                "H2O_kg": 0.0,
                "FeTiO3_kg": 0.0,
                "Metal_kg": 0.0,
                "He3_kg": 0.0,
            },
        )

        # Stock flow transaction system
        self.pending_stock_flows = []

        # Performance metrics
        self.total_power_consumed = 0
        self.step_power_consumed = 0
        self.active_operations = 0

        # Priority-as-token DRR system
        self.priorities = {}
        self.deficit_counters = {}
        self.sector_state = "active"  # active, inactive, decommissioned

        # DRR token configuration
        self.token_cost_per_turn = config.get("drr_token_cost_per_turn", 1.0)
        self.task_order = ["He3", "Metal", "Water", "Regolith", "Electrolysis"]
        self.rr_idx = 0
        self.extractor_throttle = 1.0  # 0..1 applied to extractors only

        # Initialize deficit counters for all tasks
        for t in self.task_order:
            self.deficit_counters.setdefault(t, 0.0)

    def set_priorities(self, priorities_dict):
        """
        Set manufacturing sector priorities and update sector state.

        Automatically transitions sector to inactive when all priorities are zero,
        optimizing power consumption during low-priority periods.

        Args:
            priorities_dict: Task priorities from goal-based allocation
        """
        self.priorities.update(priorities_dict)

        # Update sector state based on priorities
        if all(priority == 0.0 for priority in self.priorities.values()):
            self.sector_state = "inactive"
            self._set_all_agents_inactive()
        else:
            self.sector_state = "active"
            self._set_all_agents_active()

        # Zero deficit counters for zero-priority tasks
        for t, p in self.priorities.items():
            if p == 0.0:
                self.deficit_counters[t] = 0.0

    def _deficit_round_robin_scheduler(self):
        """
        Priority-as-token DRR scheduler with max-DC + RR tie-breaking.

        ALGORITHM:
        1. Cache task availability once
        2. Top-up tokens for runnable + positive priority tasks; zero otherwise
        3. Find max deficit among runnable tasks
        4. Round-robin tie-break among max-DC winners

        Returns:
            str: Selected task name or None if no valid tasks
        """
        if not self.priorities or all(p == 0.0 for p in self.priorities.values()):
            return None

        # Cache availability once
        avail = {t: bool(self._get_available_operations_for_task(t)) for t in self.task_order}

        # Top-up tokens (only runnable + positive priority); zero otherwise
        for t in self.task_order:
            if avail[t] and self.priorities.get(t, 0.0) > 0.0:
                self.deficit_counters[t] = self.deficit_counters.get(t, 0.0) + float(self.priorities[t])
            else:
                self.deficit_counters[t] = 0.0

        # Candidates = runnable with positive DC
        candidates = [t for t in self.task_order if avail[t] and self.deficit_counters.get(t, 0.0) > 0.0]
        if not candidates:
            return None

        # Max-DC with RR tie-break
        max_dc = max(self.deficit_counters[t] for t in candidates)
        eps = 1e-9
        winners = {t for t in candidates if self.deficit_counters[t] >= max_dc - eps}

        n = len(self.task_order)
        for k in range(n):
            idx = (self.rr_idx + k) % n
            t = self.task_order[idx]
            if t in winners:
                self.rr_idx = (idx + 1) % n
                return t
        return None

    def _execute_task(self, task):
        """
        Execute the selected manufacturing task by setting agent operational modes.

        Maps high-level manufacturing tasks to specific agent configurations:
        - He3: Requires regolith extraction + He3 generation
        - Metal: Requires regolith extraction + metal processing
        - Water: Requires ice extraction only
        - Regolith: Requires regolith extraction only
        - Electrolysis: Requires ice extraction + electrolysis generation

        Args:
            task: Manufacturing task name
        """
        task_modes = {
            "He3": ("HE3", "REGOLITH"),
            "Metal": ("METAL", "REGOLITH"),
            "Water": (None, "ICE"),
            "Regolith": (None, "REGOLITH"),
            "Electrolysis": ("ELECTROLYSIS", "ICE"),
        }

        if task in task_modes:
            generator_mode, extractor_mode = task_modes[task]
            if generator_mode:
                self._set_generator_modes(generator_mode)
            if extractor_mode:
                self._set_extractor_modes(extractor_mode)

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

    def add_stock_flow(self, source_component, consumed_resources=None, generated_resources=None):
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
                "consumed": consumed_resources or {},
                "generated": generated_resources or {},
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
        return extractor_demand * self.extractor_throttle + generator_demand

    def step(self, allocated_power):
        """
        Execute a manufacturing simulation step with priority-as-token DRR.

        EXECUTION SEQUENCE:
        1. Check sector state and power allocation
        2. Run DRR scheduler to select priority task
        3. Configure agent operational modes
        4. Execute extraction operations with available power
        5. Execute generation operations with remaining power
        6. Process all stock flows atomically
        7. Spend tokens only if work was actually done
        8. Update metrics and return unused power

        Args:
            allocated_power: Power budget allocated by world system

        Returns:
            float: Unused power returned to world system
        """
        if allocated_power <= 0 or self.sector_state == "inactive":
            return allocated_power

        selected_task = self._deficit_round_robin_scheduler()
        if selected_task is None:
            self._set_all_agents_inactive()
            return allocated_power

        self._set_all_agents_active()
        self._execute_task(selected_task)

        self.active_operations = 0
        self.step_power_consumed = 0
        remaining_power = allocated_power

        # Throttled budget for extractors
        extractor_budget = allocated_power * self.extractor_throttle
        extractor_used = 0.0

        # Execute extraction operations first (respect throttle budget)
        for extractor in self.isru_extractors:
            extractor_demand = extractor.get_power_demand()
            if extractor_demand <= 0:
                continue

            # Stop if throttle budget exhausted or no power left
            if extractor_used >= extractor_budget or remaining_power <= 0:
                break

            # Only run if full demand fits in remaining budget and power
            if extractor_demand <= remaining_power and extractor_used + extractor_demand <= extractor_budget:
                extracted_resources, power_used = extractor.extract_resources(extractor_demand)
                if extracted_resources:
                    self.add_stock_flow("ISRU_Extractor", None, extracted_resources)
                self.step_power_consumed += power_used
                remaining_power -= power_used
                extractor_used += power_used
                if power_used > 0:
                    self.active_operations += 1

        # Execute generation operations with remaining power (unthrottled)
        for generator in self.isru_generators:
            generator_demand = generator.get_power_demand()
            if generator_demand > 0 and remaining_power >= generator_demand:
                generated_resources, consumed_resources, power_used = generator.generate_resources(
                    generator_demand, self.stocks
                )
                if generated_resources:
                    self.add_stock_flow("ISRU_Generator", consumed_resources, generated_resources)
                self.step_power_consumed += power_used
                remaining_power -= power_used
                if power_used > 0:
                    self.active_operations += 1
            elif generator_demand == 0:
                generated_resources, consumed_resources, power_used = generator.generate_resources(0, self.stocks)
                if generated_resources:
                    self.add_stock_flow("ISRU_Generator_NoP", consumed_resources, generated_resources)
                    self.active_operations += 1

        self.process_all_stock_flows()
        self.total_power_consumed += self.step_power_consumed

        if selected_task is not None and self.active_operations > 0:
            dc = self.deficit_counters.get(selected_task, 0.0)
            self.deficit_counters[selected_task] = max(0.0, dc - self.token_cost_per_turn)

        return remaining_power

    def _create_metric_map(self):
        """
        Create a map of metric IDs and their corresponding values.

        Returns:
            dict: A dictionary where keys are metric IDs and values are their contributions.
        """
        metric_map = {}
        value = float(
            self.extractor_metric_contributions.get(
                "value", self.extractor_metric_contributions.get("contribution_value", 0.0)
            )
        )
        metric_map["IND-DUST-COV"] = len(self.isru_extractors) * value * self.extractor_throttle
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
            "sector_state": self.sector_state,
            "stock_H2_kg": self.stocks.get("H2_kg", 0),
            "stock_O2_kg": self.stocks.get("O2_kg", 0),
            "stock_H2O_kg": self.stocks.get("H2O_kg", 0),
            "stock_FeTiO3_kg": self.stocks.get("FeTiO3_kg", 0),
            "stock_Metal_kg": self.stocks.get("Metal_kg", 0),
            "stock_He3_kg": self.stocks.get("He3_kg", 0),
            "metric_contributions": self._create_metric_map(),
        }

    def _get_available_operations_for_task(self, task):
        """
        Check if operations are available for the given task.

        Args:
            task: Manufacturing task name

        Returns:
            bool: True if task can be executed
        """
        if task == "He3":
            # Need generators and extractors operational
            return len(self.isru_generators) > 0 and len(self.isru_extractors) > 0
        elif task == "Metal":
            # Need generators and extractors operational
            return len(self.isru_generators) > 0 and len(self.isru_extractors) > 0
        elif task == "Water":
            # Need extractors operational
            return len(self.isru_extractors) > 0
        elif task == "Regolith":
            # Need extractors operational
            return len(self.isru_extractors) > 0
        elif task == "Electrolysis":
            # Need generators and water stock
            return len(self.isru_generators) > 0 and self.stocks.get("H2O_kg", 0) > 0

        return False

    def _set_all_agents_inactive(self):
        """Set all agents to inactive state to minimize power consumption."""
        for agent in self.isru_extractors + self.isru_generators:
            if hasattr(agent, "set_agent_state"):
                agent.set_agent_state("inactive")

    def _set_all_agents_active(self):
        """Set all agents to active state for normal operations."""
        for agent in self.isru_extractors + self.isru_generators:
            if hasattr(agent, "set_agent_state"):
                agent.set_agent_state("active")
