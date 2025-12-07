"""
energy_sector.py

Simplified energy sector management with integrated power allocation.
"""

import numpy as np
from typing import List, Dict, Any
from enum import Enum

from proxima_model.components.power_generator import PowerGenerator
from proxima_model.components.power_storage import PowerStorage


class AllocationMode(Enum):
    """Power allocation strategies."""

    PROPORTIONAL = "proportional"
    EQUAL = "equal"


class EnergySector:
    """Simplified energy sector with single-step processing and allocation."""

    def __init__(self, model, config, event_bus):
        self.model = model
        self.event_bus = event_bus

        # Component collections
        self.storages: List[PowerStorage] = []
        self.generators: List[PowerGenerator] = []

        # Initialize components (preserve original initialization logic)
        for storage_cfg in config.get("storages", []):
            for _ in range(storage_cfg.get("quantity", 1)):
                self.storages.append(PowerStorage(self.model, storage_cfg))

        for gen_cfg in config.get("generators", []):
            for _ in range(gen_cfg.get("quantity", 1)):
                self.generators.append(PowerGenerator(self.model, gen_cfg))

        # Current state (moved from MicrogridManager)
        self.power_supplied = 0.0
        self.power_demanded = 0.0
        self.power_shortage = 0.0

        # Allocation mode (moved from WorldSystem)
        allocation_mode_str = (config.get("allocation_mode") or "proportional").lower()
        self.allocation_mode = AllocationMode(allocation_mode_str)

    @property
    def total_charge(self) -> float:
        """Calculate total charge across all storages."""
        return sum(s.charge_level for s in self.storages)

    @property
    def total_capacity(self) -> float:
        """Calculate total capacity across all storages."""
        return sum(s.config.max_operational_cap_kwh for s in self.storages)

    @property
    def total_state_of_charge(self) -> float:
        """Calculate overall state of charge."""
        total_cap = self.total_capacity
        return self.total_charge / total_cap if total_cap > 0 else 0

    def allocate_power(self, sector_demands: Dict[str, float]) -> Dict[str, float]:
        """
        Allocate available power among sectors based on their demands.

        Args:
            sector_demands: Dictionary of sector names to their power demands.

        Returns:
            Dictionary of sector names to allocated power amounts.
        """
        # Generate power based on total demand
        total_demand = sum(sector_demands.values())
        available_power = self.step(total_demand)

        if not sector_demands or available_power <= 0:
            return {name: 0.0 for name in sector_demands}

        # Snapshot demands (ensure non-negative)
        demands = {name: max(0.0, float(demand)) for name, demand in sector_demands.items()}
        total_demand = sum(demands.values())

        if total_demand <= 0.0:
            return {name: 0.0 for name in sector_demands}

        # Case 1: Sufficient power → satisfy all demands
        if total_demand <= available_power:
            return demands

        # Case 2: Scarcity → fair split based on allocation mode
        if self.allocation_mode == AllocationMode.EQUAL:
            num_sectors = len(sector_demands)
            per_sector = available_power / num_sectors
            return {name: min(per_sector, demands[name]) for name in sector_demands}
        else:
            # Proportional by demand (default)
            ratio = available_power / total_demand
            return {name: ratio * demands[name] for name in sector_demands}

    def step(self, power_demand):
        """Single step: process power demand and return what's available."""
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
                if remaining_excess <= 0 or storage.available_capacity <= 0:
                    continue

                power_to_charge = min(remaining_excess, storage.available_capacity / storage.config.charge_efficiency)

                if power_to_charge > 0:
                    consumed = storage.charge(power_to_charge)
                    remaining_excess -= consumed

        return self.power_supplied

    def get_metrics(self):
        """Get metrics for logging."""
        return {
            "total_power_supply_kW": self.power_supplied,
            "total_power_need_kW": self.power_demanded,
            "power_shortage_kW": self.power_shortage,
            "total_charge_level_kWh": self.total_charge,
            "total_state_of_charge": self.total_state_of_charge,
            "total_charge_capacity_kWh": self.total_capacity,
        }
