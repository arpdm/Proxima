"""
world_system.py

This module defines the WorldSystem class for the Proxima simulation engine.
It manages the simulation of a lunar microgrid, including day/night cycles, agent interactions, and data collection using Mesa.
"""

from mesa import Model
from proxima_model.components.energy_microgrid import MicrogridManager


class WorldSystem(Model):

    def __init__(self, config, seed=None):
        super().__init__(seed=seed)
        self.config = config
        self.steps = 0  # Mesa default; used by is_day
        self.daylight = self.is_day(self.steps)

        self.initialize_microgrid()
        self.running = True

    def is_day(self, t):
        lunar_day = self.config["day_hours"]
        lunar_night = self.config["night_hours"]
        cycle = lunar_day + lunar_night
        phase = t % cycle
        return 1 if phase < lunar_day else 0

    def initialize_microgrid(self):
        self.microgrid = MicrogridManager(self, config=self.config)

    def step(self):
        self.daylight = self.is_day(self.steps)
        self.microgrid.step()
        self.microgrid.advance()
        self.running = self.steps < self.config["sim_time"]

        # Updated Current Step
        self.model_metrics = {"Daylight": self.daylight}
