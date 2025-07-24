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

        # Initialize core system components
        self.initialize_microgrid()
        self.initialize_agents()

        # System-level tracking
        self.total_science = 0.0
        self.total_power_draw = 0.0
        self.model_metrics = {}

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

    def initialize_microgrid(self):
        """
        Initializes the lunar microgrid system.
        """
        self.microgrid = MicrogridManager(self, config=self.config)

    def initialize_agents(self):
        """
        Initializes all agents defined in the configuration, including science rovers.
        """
        self.science_rovers = []
        rover_configs = self.config.get("agents_config", {}).get("science_rovers", [])

        for agent_config in rover_configs:
            rover = ScienceRover(agent_config)
            self.science_rovers.append(rover)

    def get_rover_state(self):
        """
        Collects current state of all science rovers for logging.

        Returns:
            list of dict: List of per-rover status reports.
        """
        return [rover.report() for rover in self.science_rovers]

    def step(self):
        """
        Executes a single simulation step: daylight toggle, microgrid update, agent actions, and metrics.
        """
        self.daylight = self.is_day(self.steps)
        self.total_power_draw = 2

        # STEP 1: Rover loop: calculate total power demand
        for rover in self.science_rovers:
            if rover.needs_charge():
                charge_needed = rover.battery_capacity_kWh
                self.total_power_draw += charge_needed

        self.microgrid.step(self.total_power_draw)
        available_energy = self.microgrid.total_p_supply

        for rover in self.science_rovers:
            if available_energy <= 0:
                power_used, science_generated = 0.0, 0.0
                rover.status = "waiting_for_power"
                rover.is_operational = False
            else:
                power_used, science_generated = rover.step(available_energy)
                available_energy = max(0.0, available_energy - power_used)  # Clamp
                self.total_science += science_generated

        self.microgrid.advance()
        self.running = self.steps < self.config["sim_time"]

        # Updated Current Step
        self.model_metrics = {"Daylight": self.daylight, "science_generated": self.total_science}
