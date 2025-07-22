"""
energy_microgrid.py

This module defines the core classes for simulating a lunar microgrid in the Proxima project.
It includes Battery, VSAT, and FuelCell components, as well as the MicrogridManager agent for managing energy generation, storage, and supply within the simulation.
"""

import numpy as np
from mesa import Agent


class Battery:
    def __init__(self, config):
        self.config = config
        self.charge_level = config["initial_battery"]
        self.state_of_charge = self.charge_level / config["b_max"]
        self.dt = config["delta_t"]

    def charge_discharge(self, charge_request_kw):
        new_charge = self.charge_level + charge_request_kw * self.dt
        self.charge_level = np.clip(new_charge, self.config["b_min"], self.config["b_max"])
        self.state_of_charge = self.charge_level / self.config["b_max"]


class VSAT:
    def __init__(self, config):
        self.config = config
        self.generated_power_watt = 0

    def generate_power(self, power_gen_request_watts):
        self.generated_power_watt = min(self.config["p_vsat_max"], power_gen_request_watts)
        return self.generated_power_watt


class FuelCell:
    def __init__(self, config):
        self.config = config
        self.generated_power_watt = 0

    def generate_power(self, power_gen_request_watts):
        self.generated_power_watt = min(self.config["p_fuel_max"], power_gen_request_watts)
        return self.generated_power_watt


# Microgrid Manager Agent
class MicrogridManager(Agent):
    def __init__(self, model, config):
        super().__init__(model)
        self.config = config

        self.total_p_supply = 0.0
        self.p_need = config["p_need"]
        self.total_charge_level = 0.0
        self.total_state_of_charge = 0.0
        self.total_charge_capacity = 0.0
        self.batteries = []
        self.vsats = []
        self.fuel_Cells = []

        for _ in range(config["battery_count"]):
            self.batteries.append(Battery(config))

        for _ in range(config["vsat_count"]):
            self.vsats.append(VSAT(config))

        for _ in range(config["fuel_cell_count"]):
            self.fuel_Cells.append(FuelCell(config))

        self.total_charge_capacity = self.total_battery_capacity()

    def total_battery_charge(self):
        return sum(b.charge_level for b in self.batteries)

    def total_battery_capacity(self):
        return len(self.batteries) * self.config["b_max"]

    def step(self):
        self.total_charge_level = self.total_battery_charge()
        self.allowed_charge = self.total_charge_capacity - self.total_charge_level
        self.total_state_of_charge = self.total_charge_level / self.total_charge_capacity

    def advance(self):
        # If batteries are full, only generate enough power for immediate need
        if self.allowed_charge <= 0:
            temp_p_needed = self.p_need
        else:
            temp_p_needed = self.p_need + self.allowed_charge
        generated_power = 0.0

        # Generate power from VSATs or FuelCells depending on daylight
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

        self.p_vsat = sum(v.generated_power_watt for v in self.vsats)
        self.p_fuel_cells = sum(fc.generated_power_watt for fc in self.fuel_Cells)
        self.total_p_supply = self.p_vsat + self.p_fuel_cells

        net_power = self.total_p_supply - self.p_need  # Surplus (>0) or deficit (<0)
        num_batteries = len(self.batteries)

        if num_batteries > 0:
            if net_power > 0:
                # Charge batteries with surplus
                charge_per_battery = min(net_power / num_batteries, self.allowed_charge / num_batteries)
                for b in self.batteries:
                    b.charge_discharge(charge_per_battery)
            elif net_power < 0:
                # Discharge batteries to meet deficit
                discharge_per_battery = max(net_power / num_batteries, -self.total_charge_level / num_batteries)
                for b in self.batteries:
                    b.charge_discharge(discharge_per_battery)
            # If net_power == 0, no charge/discharge needed
        
        self.update_current_state()

    def update_current_state(self):
        self.agent_state = {
            "total_charge_capacity_kWh": self.total_charge_capacity,
            "total_charge_level_kWh": self.total_charge_level,
            "total_state_of_charge_%": self.total_state_of_charge,
            "total_power_supply_kW": self.total_p_supply,
            "total_power_need_kW": self.p_need,
            "generated_power_by_VSAT_kWh": self.p_vsat,
            "generated_power_by_fuel_cell_kWh ": self.p_fuel_cells,
        }
