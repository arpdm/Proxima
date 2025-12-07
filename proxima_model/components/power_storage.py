"""
Simplified energy microgrid with realistic power management.
"""

import numpy as np
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Any
from mesa import Agent


class StorageType(Enum):
    """Available storage types for expansion."""

    LI_BATTERY = auto()


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


class PowerStorage(Agent):
    """Power storage component with efficiency handling."""

    def __init__(self, model, storage_cfg: Dict[str, Any]):
        super().__init__(model)

        config = storage_cfg.get("config", storage_cfg)

        # Parse subtype with space handling
        subtype_str = storage_cfg.get("subtype", "LI_BATTERY").upper().replace(" ", "_")
        try:
            self.subtype = StorageType[subtype_str]
        except KeyError:
            self.subtype = StorageType.LI_BATTERY  # Fallback to default

        self.config = PowerStorageConfig(
            max_operational_cap_kwh=config.get("max_operational_cap_kwh", PowerStorageConfig.max_operational_cap_kwh),
            min_operational_cap_kwh=config.get("min_operational_cap_kwh", PowerStorageConfig.min_operational_cap_kwh),
            initial_charge_kwh=config.get("initial_charge_kwh", PowerStorageConfig.initial_charge_kwh),
            charge_efficiency=config.get("charge_efficiency", PowerStorageConfig.charge_efficiency),
            discharge_efficiency=config.get("discharge_efficiency", PowerStorageConfig.discharge_efficiency),
        )

        # Initialize charge level from config
        self.charge_level = self.config.initial_charge_kwh

    @property
    def state_of_charge(self) -> float:
        """Calculate state of charge as percentage."""
        return self.charge_level / self.config.max_operational_cap_kwh if self.config.max_operational_cap_kwh > 0 else 0

    @property
    def available_capacity(self) -> float:
        """Calculate available capacity for charging."""
        return self.config.max_operational_cap_kwh - self.charge_level

    @property
    def available_discharge(self) -> float:
        """Calculate available energy for discharge."""
        return max(0, self.charge_level - self.config.min_operational_cap_kwh)

    def charge(self, power_kw: float) -> float:
        """Charge battery with efficiency losses."""
        if power_kw <= 0:
            return 0
        max_charge = min(power_kw * self.config.charge_efficiency, self.available_capacity)
        self.charge_level += max_charge
        return max_charge / self.config.charge_efficiency  # Return actual power consumed

    def discharge(self, power_kw: float) -> float:
        """Discharge battery with efficiency losses."""
        if power_kw <= 0:
            return 0
        max_discharge = min(power_kw / self.config.discharge_efficiency, self.available_discharge)
        self.charge_level -= max_discharge
        return max_discharge * self.config.discharge_efficiency  # Return actual power provided
