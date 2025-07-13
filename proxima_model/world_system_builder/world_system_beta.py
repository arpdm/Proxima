"""
lunar_power_grid_simulation.py
==============================

Description:
    This is the main entry point for running the Proxima - World System Beta Phase 1

Author:
    Arpi Derm <arpiderm@gmail.com>

Created:
    July 5, 2024

Usage:
    To run the simulation, execute this script using poetry
        poetry run lunar-power-grid

License:
    MIT License

Functions:
    - main: The main function to set up and run the lunar power grid simulation.

"""

from proxima_model.tools import ts_plot as pl
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timezone

import json
import yaml
import pandas as pd
import numpy as np
import networkx as nx

from mesa import Agent, Model
from mesa.datacollection import DataCollector
from mesa.space import NetworkGrid

# Load YAML config
with open("proxima_model/environments/world_system_beta_01.yaml", "r") as f:
    CONFIG = SimpleNamespace(**json.loads(json.dumps(yaml.safe_load(f))))


# Day/night cycle
def is_day(t):
    lunar_day_hours = CONFIG.LUNAR_DAY_HOURS
    lunar_night_hours = CONFIG.LUNAR_NIGHT_HOURS  # default 14 Earth days
    cycle_length = lunar_day_hours + lunar_night_hours
    phase = t % cycle_length
    return 1 if phase < lunar_day_hours else 0


class Battery:
    def __init__(self):
        self.charge_level = CONFIG.INITIAL_BATTERY
        self.state_of_charge = self.charge_level / CONFIG.B_MAX
        self.dt = CONFIG.DELTA_T

    def chrage_discharge(self, charge_request_kw):
        new_charge = self.charge_level + charge_request_kw * self.dt
        self.charge_level = np.clip(new_charge, CONFIG.B_MIN, CONFIG.B_MAX)
        self.state_of_charge = self.charge_level / CONFIG.B_MAX


class VSAT:
    def __init__(self):
        self.generated_power_watt = 0

    def generate_power(self, power_gen_request_watts):
        self.generated_power_watt = min(CONFIG.P_VSAT_MAX, power_gen_request_watts)
        return self.generated_power_watt


class FuelCell:
    def __init__(self):
        self.generated_power_watt = 0

    def generate_power(self, power_gen_request_watts):
        self.generated_power_watt = min(CONFIG.P_FUEL_MAX, power_gen_request_watts)
        return self.generated_power_watt


# Microgrid Manager Agent
class MicrogridManager(Agent):
    def __init__(self, model):
        super().__init__(model)

        self.total_p_bat = 0.0  # Battery charge/discharge request kwh
        self.total_p_supply = 0.0  # Supplied Power kwh
        self.p_need = CONFIG.P_NEED  # Toatal power need kwh
        self.total_charge_level = 0.0  # Battery Charge Level
        self.total_state_of_charge = 0.0  # Total Battery SoC
        self.total_charge_capacity = 0.0  # Total charge capacity lwh
        self.excess_energy = 0.0  # Excess energy with no where to go
        self.batteries = []
        self.vsats = []
        self.fuel_Cells = []

        # Setup Batteries
        for _ in range(CONFIG.BATTERY_COUNT):
            battery = Battery()
            self.batteries.append(battery)

        # Setup VSATs
        for _ in range(CONFIG.VSAT_COUNT):
            vsat = VSAT()
            self.vsats.append(vsat)

        # Setup Fuel Cells
        for _ in range(CONFIG.FUEL_CELL_COUNT):
            fuel_cell = FuelCell()
            self.fuel_Cells.append(fuel_cell)

        self.total_charge_capacity = self.total_battery_capacity()

    def total_battery_charge(self):
        return sum(b.charge_level for b in self.batteries)

    def total_battery_capacity(self):
        return len(self.batteries) * CONFIG.B_MAX

    def step(self):
        # Calculate total charge level
        self.total_charge_level = self.total_battery_charge()
        self.allowed_charge = self.total_charge_capacity - self.total_charge_level

    def advance(self):

        temp_p_needed = self.p_need + self.allowed_charge  # total power needed for demand + charge
        generated_power = 0.0

        if self.model.daylight:
            for v in self.vsats:
                if temp_p_needed > 0:
                    generated = v.generate_power(temp_p_needed)
                    generated_power += generated
                    temp_p_needed -= generated
        else:
            for fc in self.fuel_Cells:
                if temp_p_needed > 0:
                    generated = fc.generate_power(temp_p_needed)
                    generated_power += generated
                    temp_p_needed -= generated

        # Store generation data
        self.p_vsat = sum(v.generated_power_watt for v in self.vsats)
        self.p_fuel_cells = sum(fc.generated_power_watt for fc in self.fuel_Cells)
        self.total_p_supply = self.p_vsat + self.p_fuel_cells

        # Battery power = generation - need
        self.total_p_bat = max(0.0, self.total_p_supply - self.p_need)

        # Distribute charge/discharge evenly
        charge_per_battery = min(self.total_p_bat / len(self.batteries), self.allowed_charge / len(self.batteries))
        for b in self.batteries:
            b.chrage_discharge(charge_per_battery)

        # Execss energy with no where to go
        self.excess_energy = abs(temp_p_needed - self.allowed_charge)


# World System Beta Model
class WorldSystemBetaModel(Model):

    def __init__(self, seed=None):
        super().__init__(seed=seed)

        # Dynamic states
        self.daylight = is_day(self.steps)

        # Create Zone Energy Infrastructure
        self.initialize_microgrid()

        # DataCollector
        self.datacollector = DataCollector(
            model_reporters={
                "Step": lambda m: int(m.steps),
                "Daylight": lambda m: m.daylight,
            },
            agent_reporters={
                "P_Need (kWh)": "p_need",
                "Total Power Supplied (kWh)": "total_p_supply",
                "Total Charge Level (kWh)": "total_charge_level",
                "Total SoC (%)": "total_state_of_charge",
                "Total Charge Capacity (kWh)": "total_charge_capacity",
                "Excess Energy (kW)": "excess_energy",
                "Battery Charge/Discharge (kwh)": "total_p_bat",
            },
        )

        # Set Model Running and start data collector
        self.running = True

    def step(self):
        # Caclulate day time
        self.daylight = is_day(self.steps)

        # Run the microgrid
        self.microgrid.do("step")
        self.microgrid.do("advance")

        # Collect data at every simulation step
        self.datacollector.collect(self)

        self.running = self.steps < CONFIG.SIM_TIME

    def initialize_microgrid(self):
        self.microgrid = MicrogridManager.create_agents(self, 1)


def main():

    # Start Simulation
    start_time = datetime.now(timezone.utc).timestamp()
    ws_1 = WorldSystemBetaModel()

    # Run Simulation
    for _ in range(CONFIG.SIM_TIME):
        ws_1.step()

    # Save Simulation Results
    results = ws_1.datacollector.get_model_vars_dataframe()
    agent_df = ws_1.datacollector.get_agent_vars_dataframe()
    agent_df.to_csv(f"log_files/WS_Beta_Agent_{start_time}.csv")
    results.to_csv(f"log_files/WS_Beta_Model_{start_time}.csv")


if __name__ == "__main__":
    main()
