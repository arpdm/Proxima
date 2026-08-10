"""
energy_sector.py

Simplified energy sector management with integrated power allocation.
"""

import numpy as np
from typing import List, Dict, Any
from enum import Enum
from dataclasses import dataclass, field

from proxima_model.components.power_generator import PowerGenerator
from proxima_model.components.power_storage import PowerStorage


class AllocationMode(Enum):
    """Power allocation strategies."""

    PROPORTIONAL = "proportional"
    EQUAL = "equal"


@dataclass
class EnergySectorState:
    """State snapshot for the energy sector."""

    power_supplied: float = 0.0
    power_demanded: float = 0.0
    power_shortage: float = 0.0
    total_charge_level_kWh: float = 0.0
    total_state_of_charge: float = 0.0
    total_charge_capacity_kWh: float = 0.0
    power_storage_count: int = 0
    power_generator_count: int = 0


class EnergySector:
    """Simplified energy sector with single-step processing and allocation."""

    def __init__(self, model, config, event_bus):
        self.model = model
        self.event_bus = event_bus

        # State container
        self.state = EnergySectorState()

        # Component collections (keep base configs for hydration top-up)
        self.storage_configs = config.get("storages", [])
        self.generator_configs = config.get("generators", [])
        self.storages: List[PowerStorage] = []
        self.generators: List[PowerGenerator] = []

        # Initialize components (preserve original initialization logic)
        for storage_cfg in self.storage_configs:
            for _ in range(storage_cfg.get("quantity", 1)):
                self.storages.append(PowerStorage(self.model, storage_cfg))

        for gen_cfg in self.generator_configs:
            for _ in range(gen_cfg.get("quantity", 1)):
                self.generators.append(PowerGenerator(self.model, gen_cfg))

        # Persist counts
        self.state.power_storage_count = len(self.storages)
        self.state.power_generator_count = len(self.generators)

        # Current state (moved from MicrogridManager)
        self.state.power_supplied = 0.0
        self.state.power_demanded = 0.0
        self.state.power_shortage = 0.0

        # Allocation mode (moved from WorldSystem)
        allocation_mode_str = (config.get("allocation_mode") or "proportional").lower()
        self.allocation_mode = AllocationMode(allocation_mode_str)

        # Hydrate from latest_state if provided
        latest_state_energy = config.get("latest_state") if isinstance(config, dict) else None
        if latest_state_energy:
            self._apply_latest_state(latest_state_energy)

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

    def _apply_latest_state(self, energy_state: Dict[str, Any]) -> None:
        """Hydrate energy metrics from latest_state snapshot."""

        self.state.power_supplied = float(energy_state.get("total_power_supply_kW", self.state.power_supplied))
        self.state.power_demanded = float(energy_state.get("total_power_need_kW", self.state.power_demanded))
        self.state.power_shortage = float(energy_state.get("power_shortage_kW", self.state.power_shortage))
        self.state.total_charge_level_kWh = float(
            energy_state.get("total_charge_level_kWh", self.state.total_charge_level_kWh)
        )
        self.state.total_charge_capacity_kWh = float(
            energy_state.get("total_charge_capacity_kWh", self.state.total_charge_capacity_kWh)
        )
        self.state.total_state_of_charge = float(
            energy_state.get("total_state_of_charge", self.state.total_state_of_charge)
        )

        # Recreate missing storages/generators if latest_state recorded more than config instantiated
        try:
            saved_storage_count = int(energy_state.get("power_storage_count", len(self.storages)))
            missing_storages = saved_storage_count - len(self.storages)
            if missing_storages > 0 and self.storage_configs:
                base_cfg = self.storage_configs[0]
                for _ in range(missing_storages):
                    self.storages.append(PowerStorage(self.model, base_cfg))
        except Exception:
            pass

        try:
            saved_generator_count = int(energy_state.get("power_generator_count", len(self.generators)))
            missing_generators = saved_generator_count - len(self.generators)
            if missing_generators > 0 and self.generator_configs:
                base_cfg = self.generator_configs[0]
                for _ in range(missing_generators):
                    self.generators.append(PowerGenerator(self.model, base_cfg))
        except Exception:
            pass

        # Update counts after potential top-up
        self.state.power_storage_count = len(self.storages)
        self.state.power_generator_count = len(self.generators)

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
        self.state.power_demanded = power_demand

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
        self.state.power_supplied = power_from_generation + total_discharged
        self.state.power_shortage = max(0, remaining_demand)

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

        # Update state of charge metrics
        self.state.total_charge_level_kWh = self.total_charge
        self.state.total_charge_capacity_kWh = self.total_capacity
        self.state.total_state_of_charge = self.total_state_of_charge

        return self.state.power_supplied

    def get_metrics(self):
        """Get metrics for logging."""
        return {
            "total_power_supply_kW": self.state.power_supplied,
            "total_power_need_kW": self.state.power_demanded,
            "power_shortage_kW": self.state.power_shortage,
            "total_charge_level_kWh": self.state.total_charge_level_kWh,
            "total_state_of_charge": self.state.total_state_of_charge,
            "total_charge_capacity_kWh": self.state.total_charge_capacity_kWh,
            "power_storage_count": self.state.power_storage_count,
            "power_generator_count": self.state.power_generator_count,
        }
