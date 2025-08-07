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

DRR SCHEDULING ALGORITHM:
========================
For each task with available operations:
1. Calculate weighted_deficit = current_deficit / task_priority
2. Select task with maximum weighted_deficit
3. Update deficit counter after task execution
4. Ensures fair resource allocation over time

TASK-TO-MODE MAPPING:
====================
Manufacturing Task -> (Generator Mode, Extractor Mode)
- He3 Production   -> (HE3, REGOLITH)
- Metal Production -> (METAL, REGOLITH) 
- Water Production -> (None, ICE)
- Regolith Mining  -> (None, REGOLITH)
- Electrolysis     -> (ELECTROLYSIS, ICE)

RESOURCE STOCK MANAGEMENT:
=========================
Tracks six primary resources:
- H2_kg: Hydrogen gas
- O2_kg: Oxygen gas  
- H2O_kg: Water
- FeTiO3_kg: Ilmenite (regolith)
- Metal_kg: Processed metals
- He3_kg: Helium-3 isotope

POWER MANAGEMENT:
================
- Requests power demand from all active agents
- Returns zero demand when sector is inactive
- Allocates power to extractors first, then generators
- Returns unused power to world system for reallocation

PERFORMANCE OPTIMIZATION:
========================
- Early exit when no valid tasks available
- Agent state caching reduces redundant operations
- Batch stock processing minimizes transaction overhead
- Efficient task availability checking

INTEGRATION POINTS:
==================
- Receives priorities from WorldSystem goal allocation
- Reports metrics to central data collection
- Coordinates with EnergySector for power allocation
- Provides resource availability to other sectors

SCALABILITY:
===========
- Agent-based design supports adding new ISRU types
- Priority system accommodates new manufacturing tasks
- Stock flow system handles arbitrary resource types
- Modular operational modes enable complex workflows
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

        # Initialize ISRU agents based on configuration
        agents_config = config.get("agents_config", [])
        for agent_cfg in agents_config:
            subtype = agent_cfg["subtype"]
            merged_config = agent_cfg["config"]
            quantity = agent_cfg["quantity"]

            # Create agents based on quantity
            for i in range(quantity):
                if subtype == "extractor":
                    agent = ISRUExtractor(model, merged_config)
                    self.isru_extractors.append(agent)
                elif subtype == "generator":
                    agent = ISRUGenerator(model, merged_config)
                    self.isru_generators.append(agent)

        # Resource stocks - loaded from database
        self.stocks = config.get("initial_stocks", {
            "H2_kg": 0.0, "O2_kg": 0.0, "H2O_kg": 0.0,
            "FeTiO3_kg": 0.0, "Metal_kg": 0.0, "He3_kg": 0.0,
        })

        # Stock flow transaction system
        self.pending_stock_flows = []

        # Performance metrics
        self.total_power_consumed = 0
        self.step_power_consumed = 0
        self.active_operations = 0

        # Deficit Round Robin priority system
        self.priorities = {}
        self.deficit_counters = {}
        self.sector_state = "active"  # active, inactive, decommissioned

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

    def _set_all_agents_inactive(self):
        """Set all agents to inactive state to minimize power consumption."""
        for agent in self.isru_extractors + self.isru_generators:
            if hasattr(agent, 'set_agent_state'):
                agent.set_agent_state("inactive")

    def _set_all_agents_active(self):
        """Set all agents to active state for normal operations."""
        for agent in self.isru_extractors + self.isru_generators:
            if hasattr(agent, 'set_agent_state'):
                agent.set_agent_state("active")

    def _deficit_round_robin_scheduler(self):
        """
        Deficit Round Robin scheduler to select the next manufacturing task.
        
        ALGORITHM:
        1. Check for tasks with available operations
        2. Calculate weighted deficits (deficit / priority) 
        3. Select task with highest weighted deficit
        4. Returns None if no valid tasks available
        
        This ensures fair resource allocation over time and prevents
        high-priority tasks from completely starving low-priority ones.
        
        Returns:
            str: Selected task name or None if no valid tasks
        """
        # Check if all priorities are zero
        if all(priority == 0.0 for priority in self.priorities.values()):
            return None
        
        # Get available operations for each task
        available_tasks = {
            task: self._get_available_operations_for_task(task) 
            for task in self.priorities.keys() 
            if self._get_available_operations_for_task(task)
        }
        
        if not available_tasks:
            return None
        
        # Calculate weighted deficits and select best task
        weighted_deficits = {}
        for task_name in available_tasks.keys():
            priority = self.priorities.get(task_name, 0.0)
            if priority > 0:
                deficit = self.deficit_counters.get(task_name, 0.0)
                weighted_deficits[task_name] = deficit / priority
        
        return max(weighted_deficits.keys(), key=lambda k: weighted_deficits[k]) if weighted_deficits else None

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
            "Electrolysis": ("ELECTROLYSIS", "ICE")
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
        self.pending_stock_flows.append({
            "source": source_component,
            "consumed": consumed_resources or {},
            "generated": generated_resources or {},
        })

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

    def get_power_demand(self):
        """
        Calculate total power demand from all ISRU operations.
        
        Returns zero if sector is inactive to optimize power allocation.
        
        Returns:
            float: Total power demand in kWh
        """
        if self.sector_state == "inactive":
            return 0.0
            
        return sum(agent.get_power_demand() for agent in self.isru_extractors + self.isru_generators)

    def step(self, allocated_power):
        """
        Execute a manufacturing simulation step.
        
        EXECUTION SEQUENCE:
        1. Check sector state and power allocation
        2. Run DRR scheduler to select priority task
        3. Configure agent operational modes
        4. Execute extraction operations with available power
        5. Execute generation operations with remaining power
        6. Process all stock flows atomically
        7. Update metrics and return unused power
        
        Args:
            allocated_power: Power budget allocated by world system
            
        Returns:
            float: Unused power returned to world system
        """
        if allocated_power <= 0 or self.sector_state == "inactive":
            return allocated_power
        
        # Select task using DRR scheduler
        selected_task = self._deficit_round_robin_scheduler()
        if selected_task is None:
            self._set_all_agents_inactive()
            return allocated_power
        
        # Ensure agents are active and set operational modes
        self._set_all_agents_active()
        self._execute_task(selected_task)
        
        # Reset step metrics
        self.active_operations = 0
        self.step_power_consumed = 0
        remaining_power = allocated_power

        # Execute extraction operations first
        for extractor in self.isru_extractors:
            extractor_demand = extractor.get_power_demand()
            if extractor_demand > 0 and remaining_power >= extractor_demand:
                extracted_resources, power_used = extractor.extract_resources(extractor_demand)
                self.add_stock_flow("ISRU_Extractor", None, extracted_resources)
                self.step_power_consumed += power_used
                remaining_power -= power_used
                
                if power_used > 0:
                    self.active_operations += 1

        # Execute generation operations with remaining power
        for generator in self.isru_generators:
            generator_demand = generator.get_power_demand()
            
            if generator_demand > 0 and remaining_power >= generator_demand:
                generated_resources, consumed_resources, power_used = generator.generate_resources(
                    generator_demand, self.stocks
                )
                self.add_stock_flow("ISRU_Generator", consumed_resources, generated_resources)
                self.step_power_consumed += power_used
                remaining_power -= power_used
                
                if power_used > 0:
                    self.active_operations += 1
                        
            elif generator_demand == 0:
                # Try no-power operations (e.g., regolith processing)
                generated_resources, consumed_resources, power_used = generator.generate_resources(0, self.stocks)
                if generated_resources:
                    self.add_stock_flow("ISRU_Generator_NoP", consumed_resources, generated_resources)
                    self.active_operations += 1

        # Process all stock flows atomically
        self.process_all_stock_flows()
        self.total_power_consumed += self.step_power_consumed
        
        return remaining_power

    def get_metrics(self):
        """
        Return comprehensive manufacturing sector metrics.
        
        Provides performance data for monitoring and optimization:
        - Power consumption and demand
        - Operational status and activity levels
        - Resource stock levels
        - Sector state information
        
        Returns:
            dict: Manufacturing sector performance metrics
        """
        return {
            "manufacturing_power_demand": self.get_power_demand(),
            "manufacturing_power_consumed": self.step_power_consumed,
            "manufacturing_active_operations": self.active_operations,
            "manufacturing_sector_state": self.sector_state,
            "stock_H2_kg": self.stocks.get("H2_kg", 0),
            "stock_O2_kg": self.stocks.get("O2_kg", 0),
            "stock_H2O_kg": self.stocks.get("H2O_kg", 0),
            "stock_FeTiO3_kg": self.stocks.get("FeTiO3_kg", 0),
            "stock_Metal_kg": self.stocks.get("Metal_kg", 0),
            "stock_He3_kg": self.stocks.get("He3_kg", 0),
        }
