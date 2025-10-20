"""
Simplified energy microgrid with realistic power management.
"""

import numpy as np
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Any
from mesa import Agent


class StorageType(Enum):
    """Available storage types for expansion."""

    LI_BATTERY = auto()
    # Add more types here as needed (e.g., FLYWHEEL = auto())


class GeneratorType(Enum):
    """Available generator types for expansion."""

    SOLAR = auto()
    NUCLEAR = auto()
    # Add more types here as needed (e.g., WIND = auto())


@dataclass
class PowerStorageConfig:
    """Configuration for power storage components."""

    max_operational_cap_kwh: float = 100.0
    min_operational_cap_kwh: float = 0.0
    initial_charge_kwh: float = 0.0
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.98

    def __post_init__(self):
        if self.max_operational_cap_kwh < 0 or self.min_operational_cap_kwh < 0:
            raise ValueError("Capacities must be non-negative")
        if self.min_operational_cap_kwh > self.max_operational_cap_kwh:
            raise ValueError("Min capacity cannot exceed max capacity")
        if not (0 < self.charge_efficiency <= 1):
            raise ValueError("Charge efficiency must be between 0 and 1")
        if not (0 < self.discharge_efficiency <= 1):
            raise ValueError("Discharge efficiency must be between 0 and 1")


@dataclass
class PowerGeneratorConfig:
    """Configuration for power generator components."""

    power_capacity_kwh: float = 10.0
    efficiency: float = 1.0
    availability: float = 1.0

    def __post_init__(self):
        if self.power_capacity_kwh < 0:
            raise ValueError("Power capacity must be non-negative")
        if not (0 < self.efficiency <= 1):
            raise ValueError("Efficiency must be between 0 and 1")
        if not (0 <= self.availability <= 1):
            raise ValueError("Availability must be between 0 and 1")


class PowerStorage:
    """Power storage component with efficiency handling."""

    def __init__(self, storage_cfg: Dict[str, Any]):
        config = storage_cfg.get("config", storage_cfg)

        # Parse subtype with space handling
        subtype_str = storage_cfg.get("subtype", "LI_BATTERY").upper().replace(" ", "_")
        try:
            self.subtype = StorageType[subtype_str]
        except KeyError:
            self.subtype = StorageType.LI_BATTERY  # Fallback to default

        # Initialize using config values (preserve original behavior)
        self.charge_level = config.get("initial_charge_kwh", 0)
        self.capacity = config.get("max_operational_cap_kwh", 100)
        self.min_charge = config.get("min_operational_cap_kwh", 0)
        self.charge_efficiency = config.get("charge_efficiency", 0.95)
        self.discharge_efficiency = config.get("discharge_efficiency", 0.98)

    @property
    def state_of_charge(self) -> float:
        """Calculate state of charge as percentage."""
        return self.charge_level / self.capacity if self.capacity > 0 else 0

    @property
    def available_capacity(self) -> float:
        """Calculate available capacity for charging."""
        return self.capacity - self.charge_level

    @property
    def available_discharge(self) -> float:
        """Calculate available energy for discharge."""
        return max(0, self.charge_level - self.min_charge)

    def charge(self, power_kw: float) -> float:
        """Charge battery with efficiency losses."""
        if power_kw <= 0:
            return 0
        max_charge = min(power_kw * self.charge_efficiency, self.available_capacity)
        self.charge_level += max_charge
        return max_charge / self.charge_efficiency  # Return actual power consumed

    def discharge(self, power_kw: float) -> float:
        """Discharge battery with efficiency losses."""
        if power_kw <= 0:
            return 0
        max_discharge = min(power_kw / self.discharge_efficiency, self.available_discharge)
        self.charge_level -= max_discharge
        return max_discharge * self.discharge_efficiency  # Return actual power provided


class PowerGenerator:
    """Power generator component."""

    def __init__(self, gen_cfg: Dict[str, Any]):
        config = gen_cfg.get("config", gen_cfg)

        # Parse subtype with space handling
        subtype_str = gen_cfg.get("subtype", "SOLAR").upper().replace(" ", "_")
        try:
            self.subtype = GeneratorType[subtype_str]
        except KeyError:
            self.subtype = GeneratorType.SOLAR  # Fallback to default

        # Initialize using config values (preserve original behavior)
        self.capacity = config.get("power_capacity_kwh", 10)
        self.efficiency = config.get("efficiency", 1.0)
        self.availability = config.get("availability", 1.0)
        self.current_output_kwh = 0

    def generate(self, max_needed_kw: float) -> float:
        """Generate power based on conditions and actual need."""
        max_output = self.capacity * self.efficiency * self.availability
        self.current_output_kwh = min(max_output, max_needed_kw)
        return self.current_output_kwh


class MicrogridManager(Agent):
    """Simplified microgrid with realistic power flow."""

    def __init__(self, model, config: Dict[str, Any]):
        super().__init__(model)

        # Component collections
        self.storages: List[PowerStorage] = []
        self.generators: List[PowerGenerator] = []

        # Initialize components (preserve original initialization logic)
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
    def total_charge(self) -> float:
        """Calculate total charge across all storages."""
        return sum(s.charge_level for s in self.storages)

    @property
    def total_capacity(self) -> float:
        """Calculate total capacity across all storages."""
        return sum(s.capacity for s in self.storages)

    @property
    def total_state_of_charge(self) -> float:
        """Calculate overall state of charge."""
        total_cap = self.total_capacity
        return self.total_charge / total_cap if total_cap > 0 else 0

    def step(self, power_demand: float) -> float:
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
                if remaining_excess <= 0 or storage.available_capacity <= 0:
                    continue

                power_to_charge = min(remaining_excess, storage.available_capacity / storage.charge_efficiency)

                if power_to_charge > 0:
                    consumed = storage.charge(power_to_charge)
                    remaining_excess -= consumed

        return self.power_supplied

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics for logging."""
        return {
            "total_power_supply_kW": self.power_supplied,
            "total_power_need_kW": self.power_demanded,
            "power_shortage_kW": self.power_shortage,
            "total_charge_level_kWh": self.total_charge,
            "total_state_of_charge": self.total_state_of_charge,
            "total_charge_capacity_kWh": self.total_capacity,
        }
