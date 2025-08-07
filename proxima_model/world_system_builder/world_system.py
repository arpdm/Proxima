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

GOAL SYSTEM INTEGRATION:
=======================
Goals are loaded from MongoDB and define:
- sector_weights: How much each goal influences sector task priorities
- power_allocation: Ratio of total power each sector receives for this goal
- priority_weight: Base importance multiplier for the goal

Example Goal Structure:
{
  "name": "He3 Production",
  "priority_weight": 80,
  "sector_weights": {
    "manufacturing": {
      "He3": 100,         // Task priority weight
      "Regolith": 60,     // Supporting task weight
      "power_allocation": 0.7  // 70% of power to manufacturing
    },
    "science": {
      "power_allocation": 0.3    // 30% of power to science
    }
  }
}

SCALABILITY:
===========
- Database-driven configuration allows runtime goal modification
- Sector-based architecture supports adding new operational domains
- Metric collection framework enables performance monitoring and optimization
- Mesa framework integration provides agent-based modeling capabilities

DEPENDENCIES:
============
- Mesa: Agent-based modeling framework
- MongoDB: Goal and configuration storage
- Sector Classes: EnergySector, ScienceSector, ManufacturingSector
"""

from mesa import Model
from proxima_model.sphere_engine.energy_sector import EnergySector
from proxima_model.sphere_engine.science_sector import ScienceSector
from proxima_model.sphere_engine.manufacturing_sector import ManufacturingSector


class WorldSystem(Model):
    def __init__(self, config, seed=None):
        super().__init__(seed=seed)
        self.config = config
        self.running = True
        
        # Sector registry for dynamic management
        self.sectors = {}
        
        # Initialize sectors dynamically
        self._initialize_sectors()
        
        # Load goals from configuration
        goals_config = self.config.get("goals", {})
        self.active_goals = goals_config.get("active_goals", [])
    
    def _initialize_sectors(self):
        """Initialize all sectors dynamically based on configuration."""
        agents_config = self.config.get("agents_config", {})
        
        if "energy" in agents_config:
            self.sectors["energy"] = EnergySector(self, agents_config["energy"])
            
        if "science" in agents_config:
            self.sectors["science"] = ScienceSector(agents_config["science"])
            
        if "manufacturing" in agents_config:
            self.sectors["manufacturing"] = ManufacturingSector(self, agents_config["manufacturing"])
    
    def _calculate_sector_allocations(self, available_power):
        """
        Calculate power and priority allocations based on loaded goals configuration.
        
        ALGORITHM:
        1. Iterate through all active goals from database
        2. Extract power allocation ratios for each sector per goal
        3. Apply goal priority weights to calculate weighted allocations
        4. Build dynamic priority matrix for all sectors
        5. Normalize power ratios and allocate based on actual demands
        
        Returns:
            tuple: (sector_power_allocations_dict, sector_priorities_dict)
        """
        sector_power_weights = {}
        sector_priorities = {}
        
        # Initialize known sectors
        known_sectors = ["science", "manufacturing"]
        for sector_name in known_sectors:
            sector_power_weights[sector_name] = 0.0
            sector_priorities[sector_name] = {}

        # Process each active goal
        for goal in self.active_goals:
            goal_weight = goal["priority_weight"]
            sector_weights = goal["sector_weights"]

            for sector_name, sector_config in sector_weights.items():
                # Initialize sector if not seen before
                if sector_name not in sector_power_weights:
                    sector_power_weights[sector_name] = 0.0
                    sector_priorities[sector_name] = {}

                # Calculate power weights
                if isinstance(sector_config, dict):
                    power_alloc = sector_config.get("power_allocation", 0.0)
                    sector_power_weights[sector_name] += goal_weight * power_alloc

                    # Build task priorities for this sector
                    for task, task_weight in sector_config.items():
                        if task != "power_allocation":
                            current_priority = sector_priorities[sector_name].get(task, 0.0)
                            sector_priorities[sector_name][task] = current_priority + (goal_weight * task_weight)

        # Normalize power allocation
        total_power_weight = sum(sector_power_weights.values())
        sector_power_ratios = {}
        
        if total_power_weight > 0:
            for sector_name, weight in sector_power_weights.items():
                sector_power_ratios[sector_name] = weight / total_power_weight
        else:
            # Equal distribution as fallback
            num_sectors = len(sector_power_weights)
            for sector_name in sector_power_weights:
                sector_power_ratios[sector_name] = 1.0 / num_sectors if num_sectors > 0 else 0.0

        # Calculate actual power demands and allocations
        sector_demands = {}
        sector_allocated = {}
        
        # Get demands from all operational sectors dynamically
        for sector_name, sector in self.sectors.items():
            if sector_name != "energy" and hasattr(sector, 'get_power_demand'):
                sector_demands[sector_name] = sector.get_power_demand()

        total_demand = sum(sector_demands.values())

        if total_demand <= available_power:
            # Sufficient power for all demands
            sector_allocated = sector_demands.copy()
        else:
            # Insufficient power - allocate based on goal ratios
            for sector_name, demand in sector_demands.items():
                ratio = sector_power_ratios.get(sector_name, 0.0)
                allocated = min(demand, available_power * ratio)
                sector_allocated[sector_name] = allocated

        return sector_allocated, sector_priorities

    def step(self):
        """Execute a single simulation step with dynamic sector handling."""
        # Calculate total power demand from all non-energy sectors
        operational_sectors = {name: sector for name, sector in self.sectors.items() if name != "energy"}
        total_power_demand = sum(sector.get_power_demand() for sector in operational_sectors.values())
        
        # Generate available power
        energy_sector = self.sectors.get("energy")
        available_power = energy_sector.step(total_power_demand) if energy_sector else 0
        
        # Calculate allocations
        sector_allocated, sector_priorities = self._calculate_sector_allocations(available_power)
        
        # Execute all sectors with their allocations
        for sector_name, sector in operational_sectors.items():
            allocated_power = sector_allocated.get(sector_name, 0)
            priorities = sector_priorities.get(sector_name, {})
            
            # Set priorities if sector supports them
            if hasattr(sector, 'set_priorities') and priorities:
                sector.set_priorities(priorities)
            
            # Execute sector
            sector.step(allocated_power)
        
        # Collect metrics
        self._collect_metrics()
    
    def _collect_metrics(self):
        """Collect metrics from all sectors dynamically."""
        self.model_metrics = {
            "environment": {"step": self.steps},
        }
        
        for sector_name, sector in self.sectors.items():
            if hasattr(sector, 'get_metrics'):
                self.model_metrics[sector_name] = sector.get_metrics()
