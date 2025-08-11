"""
Simplified energy microgrid with realistic power management.
"""

import numpy as np
from mesa import Agent


class PowerStorage:
    def __init__(self, storage_cfg):
        config = storage_cfg.get("config", storage_cfg)
        self.subtype = storage_cfg.get("subtype", "battery")
        self.charge_level = config.get("initial_charge_kwh", 0)
        self.capacity = config.get("max_operational_cap_kwh", 100)
        self.min_charge = config.get("min_operational_cap_kwh", 0)
        self.charge_efficiency = config.get("charge_efficiency", 0.95)
        self.discharge_efficiency = config.get("discharge_efficiency", 0.98)

    @property
    def state_of_charge(self):
        return self.charge_level / self.capacity if self.capacity > 0 else 0

    @property
    def available_capacity(self):
        return self.capacity - self.charge_level

    @property
    def available_discharge(self):
        return max(0, self.charge_level - self.min_charge)

    def charge(self, power_kw):
        """Charge battery with efficiency losses."""
        if power_kw <= 0:
            return 0
        max_charge = min(power_kw * self.charge_efficiency, self.available_capacity)
        self.charge_level += max_charge
        return max_charge / self.charge_efficiency  # Return actual power consumed

    def discharge(self, power_kw):
        """Discharge battery with efficiency losses."""
        if power_kw <= 0:
            return 0
        max_discharge = min(power_kw / self.discharge_efficiency, self.available_discharge)
        self.charge_level -= max_discharge
        return max_discharge * self.discharge_efficiency  # Return actual power provided


class PowerGenerator:
    def __init__(self, gen_cfg):
        config = gen_cfg.get("config", gen_cfg)
        self.subtype = gen_cfg.get("subtype")
        self.capacity = config.get("power_capacity_kwh", 10)
        self.efficiency = config.get("efficiency", 1.0)
        self.current_output_kwh = 0

    def generate(self, max_needed_kw):
        """Generate power based on conditions and actual need."""
        max_output = self.capacity * self.efficiency
        self.current_output_kwh = min(max_output, max_needed_kw)
        return self.current_output_kwh


class MicrogridManager(Agent):
    """Simplified microgrid with realistic power flow."""

    def __init__(self, model, config):
        super().__init__(model)
        self.storages = []
        self.generators = []

        # Initialize components
        for storage_cfg in config.get("storages", []):
            for _ in range(storage_cfg.get("quantity", 1)):
                self.storages.append(PowerStorage(storage_cfg))

        for gen_cfg in config.get("generators", []):
            for _ in range(gen_cfg.get("quantity", 1)):
                self.generators.append(PowerGenerator(gen_cfg))

        # Current state
        self.power_supplied = 0.0
        self.power_demanded = 0.0
        self.power_shortage = 0.0

    @property
    def total_charge(self):
        return sum(s.charge_level for s in self.storages)

    @property
    def total_capacity(self):
        return sum(s.capacity for s in self.storages)

    @property
    def total_state_of_charge(self):
        return self.total_charge / self.total_capacity if self.total_capacity > 0 else 0

    def step(self, power_demand):
        """Single step: handle power demand with generation and storage."""
        self.power_demanded = power_demand

        # 1. Calculate total power that could be useful
        total_storage_capacity = sum(s.available_capacity for s in self.storages)
        max_useful_power = power_demand + (total_storage_capacity / 0.95)  # Account for charge efficiency

        # 2. Generate power based on actual need (demand + storage capacity)
        total_generated = 0
        remaining_useful_power = max_useful_power

        for gen in self.generators:
            generated = gen.generate(remaining_useful_power)
            total_generated += generated
            remaining_useful_power -= generated
            if remaining_useful_power <= 0:
                break

        # 3. Try to meet demand with generation first
        power_from_generation = min(total_generated, power_demand)
        remaining_demand = power_demand - power_from_generation

        # 4. If demand not met, use battery storage
        total_discharged = 0
        if remaining_demand > 0:
            for storage in self.storages:
                if remaining_demand <= 0:
                    break
                discharged = storage.discharge(remaining_demand)
                total_discharged += discharged
                remaining_demand -= discharged

        # 5. Calculate what we actually supplied
        self.power_supplied = power_from_generation + total_discharged
        self.power_shortage = max(0, remaining_demand)

        # 6. Charge batteries with excess generation (should be minimal now)
        excess_power = total_generated - power_from_generation
        if excess_power > 0:
            remaining_excess = excess_power
            for storage in self.storages:
                if remaining_excess <= 0:
                    break
                if storage.available_capacity <= 0:
                    continue

                power_to_charge = min(remaining_excess, storage.available_capacity / storage.charge_efficiency)

                if power_to_charge > 0:
                    consumed = storage.charge(power_to_charge)
                    remaining_excess -= consumed

        return self.power_supplied

    def get_metrics(self):
        """Get current metrics for logging."""
        return {
            "total_power_supply_kW": self.power_supplied,
            "total_power_need_kW": self.power_demanded,
            "power_shortage_kW": self.power_shortage,
            "total_charge_level_kWh": self.total_charge,
            "total_state_of_charge": self.total_state_of_charge,
            "total_charge_capacity_kWh": self.total_capacity,
        }
