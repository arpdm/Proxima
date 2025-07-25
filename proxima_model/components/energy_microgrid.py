"""
energy_microgrid.py

Generalized microgrid simulation for the Proxima project.
Supports dynamic power generators and storages, with runtime config injection.
"""

import numpy as np
from mesa import Agent


# Generalized Power Storage
class PowerStorage:
    def __init__(self, storage_cfg):
        # Accept the full storage config dict (with subtype, etc.)
        config = storage_cfg.get("config", storage_cfg)
        self.subtype = storage_cfg.get("subtype", "unknown")
        self.config = config
        self.charge_level = config.get("initial_charge_kwh", config.get("b_min", 0))
        self.b_min = config.get("min_operational_cap_kwh", config.get("b_min", 0))
        self.b_max = config.get("max_operational_cap_kwh", config.get("b_max", 100))
        self.dt = config.get("delta_t", 1)
        self.state_of_charge = self.charge_level / self.b_max if self.b_max else 0

    def charge_discharge(self, charge_request_kw):
        new_charge = self.charge_level + charge_request_kw * self.dt
        self.charge_level = np.clip(new_charge, self.b_min, self.b_max)
        self.state_of_charge = self.charge_level / self.b_max if self.b_max else 0


# Generalized Power Generator
class PowerGenerator:
    def __init__(self, gen_cfg):
        # Accept the full generator config dict (with subtype, etc.)
        config = gen_cfg.get("config", gen_cfg)
        self.subtype = gen_cfg.get("subtype", "unknown")
        self.config = config
        self.efficiency = config.get("efficiency", 1.0)
        self.availability = config.get("availability", 1.0)
        self.power_capacity = config.get("power_capacity_kwh")
        self.generated_power_watt = 0

    def generate_power(self, power_gen_request_kwh, daylight=1):
        # Only generate if available (e.g. solar only in daylight)
        if self.subtype == "solar" and not daylight:
            self.generated_power_watt = 0
        else:
            available_power = self.power_capacity * self.efficiency * self.availability
            self.generated_power_watt = min(available_power, power_gen_request_kwh)
        return self.generated_power_watt


# Microgrid Manager Agent (Generalized)
class MicrogridManager(Agent):
    def __init__(self, model, config):
        super().__init__(model)
        self.config = config

        self.total_p_supply = 0.0
        self.p_need = config.get("p_need", 2.0)
        self.total_charge_level = 0.0
        self.total_state_of_charge = 0.0
        self.total_charge_capacity = 0.0

        # Generalized lists
        self.storages = []
        self.generators = []

        # Instantiate storages using quantity field
        for storage_cfg in config.get("storages", []):
            quantity = storage_cfg.get("quantity", 1)
            for _ in range(quantity):
                self.storages.append(PowerStorage(storage_cfg))

        # Instantiate generators using quantity field
        for gen_cfg in config.get("generators", []):
            quantity = gen_cfg.get("quantity", 1)
            for _ in range(quantity):
                self.generators.append(PowerGenerator(gen_cfg))
        
        self.total_charge_capacity = self.total_storage_capacity()

    def total_storage_charge(self):
        return sum(s.charge_level for s in self.storages)

    def total_storage_capacity(self):
        return sum(s.b_max for s in self.storages)

    def step(self, power_need):
        self.total_charge_level = self.total_storage_charge()
        self.allowed_charge = self.total_charge_capacity - self.total_charge_level
        self.total_state_of_charge = (
            self.total_charge_level / self.total_charge_capacity if self.total_charge_capacity else 0
        )
        self.p_need = power_need

    def advance(self):
        # Determine total power needed (immediate + allowed charge)
        temp_p_needed = self.p_need + max(self.allowed_charge, 0)
        generated_power = 0.0

        # Generate power from all generators (respecting daylight for solar)
        for gen in self.generators:
            generated = gen.generate_power(temp_p_needed, daylight=self.model.daylight)
            generated_power += generated
            temp_p_needed -= generated

        self.total_p_supply = generated_power

        net_power = self.total_p_supply - self.p_need  # Surplus (>0) or deficit (<0)
        num_storages = len(self.storages)

        if num_storages > 0:
            if net_power > 0:
                # Charge storages with surplus
                charge_per_storage = min(net_power / num_storages, self.allowed_charge / num_storages)
                for s in self.storages:
                    s.charge_discharge(charge_per_storage)
            elif net_power < 0:
                # Discharge storages to meet deficit
                discharge_per_storage = max(net_power / num_storages, -self.total_charge_level / num_storages)
                for s in self.storages:
                    s.charge_discharge(discharge_per_storage)
            # If net_power == 0, no charge/discharge needed

        self.update_current_state()

    def update_current_state(self):
        self.agent_state = {
            "total_charge_capacity_kWh": self.total_charge_capacity,
            "total_charge_level_kWh": self.total_charge_level,
            "total_state_of_charge_%": self.total_state_of_charge,
            "total_power_supply_kW": self.total_p_supply,
            "total_power_need_kW": self.p_need,
            "generator_status": [
                {
                    "subtype": gen.subtype,
                    "generated_power_kWh": gen.generated_power_watt,
                    "efficiency": gen.efficiency,
                    "availability": gen.availability,
                    "capacity": gen.power_capacity,
                }
                for gen in self.generators
            ],
            "storage_status": [
                {
                    "subtype": s.subtype,
                    "charge_level": s.charge_level,
                    "state_of_charge": s.state_of_charge,
                    "capacity": s.b_max,
                }
                for s in self.storages
            ],
        }
