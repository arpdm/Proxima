"""
Power Generator
"""

import numpy as np
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Any
from mesa import Agent


class GeneratorType(Enum):
    """Available generator types for expansion."""

    SOLAR = auto()
    NUCLEAR = auto()
    # Add more types here as needed (e.g., WIND = auto())


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


class PowerGenerator(Agent):
    """Power generator component."""

    def __init__(self, model, gen_cfg: Dict[str, Any]):
        super().__init__(model)

        config = gen_cfg.get("config", gen_cfg)

        # Parse subtype with space handling
        subtype_str = gen_cfg.get("subtype", "SOLAR").upper().replace(" ", "_")
        try:
            self.subtype = GeneratorType[subtype_str]
        except KeyError:
            self.subtype = GeneratorType.SOLAR  # Fallback to default

        self.config = PowerGeneratorConfig(
            power_capacity_kwh=config.get("power_capacity_kwh", PowerGeneratorConfig.power_capacity_kwh),
            efficiency=config.get("efficiency", PowerGeneratorConfig.efficiency),
            availability=config.get("availability", PowerGeneratorConfig.availability),
        )

        self.current_output_kwh = 0

    def generate(self, max_needed_kw: float) -> float:
        """Generate power based on conditions and actual need."""
        max_output = self.config.power_capacity_kwh * self.config.efficiency * self.config.availability
        self.current_output_kwh = min(max_output, max_needed_kw)
        return self.current_output_kwh
