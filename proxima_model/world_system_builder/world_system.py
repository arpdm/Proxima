"""
world_system.py

Defines the WorldSystem class for the Proxima simulation engine.
Manages the simulation of a lunar microgrid, including day/night cycles,
agent interactions, and data collection using Mesa.
"""

from mesa import Model
from proxima_model.components.energy_microgrid import MicrogridManager
from proxima_model.components.sceince_rover import ScienceRover


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

        # Energy Sector
        self.initialize_microgrid()

        # Science Sector
        self.initialize_agents()

        # System-level tracking
        self.total_science = 0.0
        self.total_power_draw = 0.0
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

    # ------------------ Energy Sector ------------------
    def initialize_microgrid(self):
        """Initializes the lunar microgrid system."""
        microgrid_config = {
            "generators": self.config.get("agents_config", {}).get("generators", []),
            "storages": self.config.get("agents_config", {}).get("storages", []),
            "p_need": self.config.get("p_need", 2.0)
        }
        self.microgrid = MicrogridManager(self, config=microgrid_config)

    def update_microgrid(self, power_draw):
        """Steps the microgrid and returns available energy."""
        self.microgrid.step(power_draw)
        return self.microgrid.total_p_supply

    def advance_microgrid(self):
        """Advances the microgrid state."""
        self.microgrid.advance()

    # ------------------ Science Sector ------------------
    def initialize_agents(self):
        """Initializes all science rovers."""
        self.science_rovers = []
        rover_configs = self.config.get("agents_config", {}).get("science_rovers", [])
        for agent_config in rover_configs:
            quantity = agent_config.get("quantity", 1)
            for _ in range(quantity):
                rover = ScienceRover(agent_config)
                self.science_rovers.append(rover)

    def calculate_rover_power_demand(self):
        """Calculates total power demand from rovers needing charge."""
        total_power = 2  # baseline
        for rover in self.science_rovers:
            if rover.needs_charge():
                total_power += rover.battery_capacity_kWh
        return total_power

    def update_rovers(self, available_energy):
        """Updates rover states based on available energy."""
        for rover in self.science_rovers:
            if available_energy <= 0:
                power_used, science_generated = 0.0, 0.0
                rover.status = "waiting_for_power"
                rover.is_operational = False
            else:
                power_used, science_generated = rover.step(available_energy)
                available_energy = max(0.0, available_energy - power_used)
                self.total_science += science_generated

    def get_rover_state(self):
        """Returns current state of all science rovers."""
        return [rover.report() for rover in self.science_rovers]

    # ------------------ Simulation Step ------------------
    def step(self):
        """
        Executes a single simulation step: daylight toggle, microgrid update, agent actions, and metrics.
        """
        self.daylight = self.is_day(self.steps)

        self.total_power_draw = self.calculate_rover_power_demand()
        available_energy = self.update_microgrid(self.total_power_draw)

        # Track science generated THIS step (not cumulative)
        step_science = 0.0
        for rover in self.science_rovers:
            if available_energy <= 0:
                power_used, science_generated = 0.0, 0.0
                rover.status = "waiting_for_power"
                rover.is_operational = False
            else:
                power_used, science_generated = rover.step(available_energy)
                available_energy = max(0.0, available_energy - power_used)
                step_science += science_generated

        # Update cumulative total
        self.total_science += step_science

        self.advance_microgrid()

        self.running = self.steps < self.config["sim_time"]

        # Log step-level metrics (not cumulative)
        self.model_metrics = {
            "Daylight": self.daylight,
            "science_generated": science_generated,
            "total_science_cumulative": self.total_science
        }
