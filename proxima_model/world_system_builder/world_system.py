"""
world_system.py

Defines the WorldSystem class for the Proxima simulation engine.
Manages the simulation of a lunar microgrid, including day/night cycles,
agent interactions, and data collection using Mesa.
"""

from mesa import Model
from proxima_model.sphere_engine.energy_sector import EnergySector
from proxima_model.sphere_engine.science_sector import ScienceSector


class WorldSystem(Model):
    def __init__(self, config, seed=None):
        """
        Initializes the world system simulation model.

        Args:
            config (dict): Simulation configuration, including environment and agent definitions.
            seed (int, optional): Random seed for reproducibility.
        """
        super().__init__(seed=seed)
        self.config = config
        self.steps = 0
        self.daylight = self.is_day(self.steps)
        self.running = True

        # Initialize sectors
        self.initialize_energy_sector()
        self.initialize_science_sector()

        # System-level tracking
        self.model_metrics = {}

    # ------------------ Environment & Time ------------------
    def is_day(self, t):
        """
        Determines whether the current simulation step is during lunar day.

        Args:
            t (int): Simulation timestep.

        Returns:
            int: 1 if it's day, 0 if night.
        """
        lunar_day = self.config["day_hours"]
        lunar_night = self.config["night_hours"]
        cycle = lunar_day + lunar_night
        phase = t % cycle
        return 1 if phase < lunar_day else 0

    # ================== Initialize World System Sectors ===================== #

    def initialize_science_sector(self):
        """Initialize the science sector."""
        science_config = self.config.get("agents_config", {})
        self.science_sector = ScienceSector(science_config)

    def initialize_energy_sector(self):
        """Initialize the energy sector."""
        energy_config = {
            "generators": self.config.get("agents_config", {}).get("generators", []),
            "storages": self.config.get("agents_config", {}).get("storages", []),
            "p_need": self.config.get("p_need", 2.0)
        }
        self.energy_sector = EnergySector(self, energy_config)

    # ================= Run World System ===================================== #
    
    def step(self):
        """
        Executes a single simulation step: daylight toggle, energy management, science operations, and metrics.
        """
        self.steps += 1
        self.daylight = self.is_day(self.steps)

        # Get total power demand from all sectors
        science_power_demand = self.science_sector.get_power_demand()
        
        # Energy sector processes demand and returns available power
        available_energy = self.energy_sector.step(science_power_demand)
        
        # Science sector operates with whatever power is available
        self.science_sector.step(available_energy)

        # Check if simulation should continue
        sim_time = self.config.get("sim_time")
        if sim_time is not None:
            self.running = self.steps < sim_time
        else:
            self.running = True

        # Get metrics from each sector and organize by sector
        self.model_metrics = {
            "environment": {
                "daylight": self.daylight,
                "step": self.steps,
            },
            "energy": self.energy_sector.get_metrics(),
            "science": self.science_sector.get_metrics(),
        }