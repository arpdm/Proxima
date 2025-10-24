"""
ISRU (In-Situ Resource Utilization) Agents for lunar resource extraction and generation.
"""

import numpy as np
import logging

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Tuple
from mesa import Agent

logger = logging.getLogger(__name__)


class ISRUMode(Enum):
    """Available ISRU operational modes."""

    ICE_EXTRACTION = "ICE_EXTRACTION"
    REGOLITH_EXTRACTION = "REGOLITH_EXTRACTION"
    HE3_GENERATION = "HE3_GENERATION"
    INACTIVE = "INACTIVE"


@dataclass
class ISRUConfig:
    """Configuration for ISRU agents."""

    # Extraction capabilities
    ice_extraction_power_kWh: float = 5.0
    ice_extraction_output_kg: float = 20.0
    regolith_extraction_power_kWh: float = 10.0
    regolith_extraction_output_kg: float = 100.0

    # Generation capabilities
    he3_extraction_power_kWh: float = 50.0
    he3_regolith_processing_throughput_tons_per_step: float = 100.0

    # Common parameters
    max_power_usage_kWh: float = 65.0
    efficiency: float = 0.9
    processing_time_t: int = 3
    isru_modes: List[str] = field(
        default_factory=lambda: ["ICE_EXTRACTION", "REGOLITH_EXTRACTION", "HE3_GENERATION", "INACTIVE"]
    )

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not (0 < self.efficiency <= 1):
            raise ValueError(f"Efficiency must be between 0 and 1, got {self.efficiency}")
        if self.processing_time_t < 0:
            raise ValueError("Processing time must be non-negative")


@dataclass
class He3Concentration:
    """He-3 concentration parameters."""

    min_ppb: float
    max_ppb: float
    mode_ppb: float = field(init=False)

    def __post_init__(self):
        self.mode_ppb = (self.min_ppb + self.max_ppb) / 2


class ISRUAgent(Agent):
    """Unified ISRU Agent - handles both extraction and generation tasks."""

    def __init__(self, model, config: dict):
        super().__init__(model)

        # Create configuration dataclass from dict
        self.config = ISRUConfig(**{k: v for k, v in config.items() if k in ISRUConfig.__dataclass_fields__})

        # Agent identification
        self.agent_type = "isru"
        self.subtype = "robot"

        # Setup He-3 concentration parameters from environment
        self.he3_concentration = self._setup_he3_parameters(model)

        try:
            self.operational_mode = ISRUMode(self.config.isru_modes[0])
        except (ValueError, IndexError):
            self.operational_mode = ISRUMode.INACTIVE

        # Cache power demands for efficiency
        self._power_demand_cache = {
            ISRUMode.ICE_EXTRACTION: self.config.ice_extraction_power_kWh,
            ISRUMode.REGOLITH_EXTRACTION: self.config.regolith_extraction_power_kWh,
            ISRUMode.HE3_GENERATION: self.config.he3_extraction_power_kWh,
            ISRUMode.INACTIVE: 0.0,
        }

    def _setup_he3_parameters(self, model) -> He3Concentration:
        """Setup He-3 concentration parameters from model configuration."""

        # Find helium3 resource configuration
        he3_config = next(
            (res for res in model.config.get("resources", []) if res.get("resource") == "helium3"),
            {"density_ppb": [3, 8]},  # Default fallback
        )

        density_range = he3_config.get("density_ppb", [3, 8])
        return He3Concentration(min_ppb=float(density_range[0]), max_ppb=float(density_range[1]))

    def set_operational_mode(self, mode: str) -> None:
        """Set the operational mode for this ISRU agent."""
        try:
            self.operational_mode = ISRUMode(mode)
        except ValueError:
            available_modes = [mode.value for mode in ISRUMode]
            logger.error(f"Invalid mode {mode}. Available modes: {available_modes}")

    def get_power_demand(self) -> float:
        """Return current power demand based on operational mode."""
        return self._power_demand_cache[self.operational_mode]

    def perform_operation(
        self, allocated_power: float, stocks: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """Perform operation based on current mode."""

        power_needed = self.get_power_demand()

        # Check if we have enough power to operate
        if allocated_power < power_needed:
            return {}, {}, 0.0

        # Route to appropriate operation method based on mode
        if self.operational_mode in [ISRUMode.ICE_EXTRACTION, ISRUMode.REGOLITH_EXTRACTION]:
            return self._perform_extraction()
        elif self.operational_mode == ISRUMode.HE3_GENERATION:
            return self._perform_he3_generation()
        elif self.operational_mode == ISRUMode.INACTIVE:
            return {}, {}, 0.0

        return {}, {}, 0.0

    def _perform_extraction(self) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """Perform extraction operations."""
        extracted_resources = self._generate_extraction_output()
        return extracted_resources, {}, self.get_power_demand()

    def _generate_extraction_output(self) -> Dict[str, float]:
        """Generate output based on current extraction mode."""
        if self.operational_mode == ISRUMode.ICE_EXTRACTION:
            output = self.config.ice_extraction_output_kg * self.config.efficiency
            return {"H2O_kg": output}
        elif self.operational_mode == ISRUMode.REGOLITH_EXTRACTION:
            output = self.config.regolith_extraction_output_kg * self.config.efficiency
            return {"FeTiO3_kg": output}
        return {}

    def _perform_he3_generation(self) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """Perform generation operations."""

        # Generate He-3 concentration using triangular distribution
        helium_concentration_ppb = np.random.triangular(
            self.he3_concentration.min_ppb, self.he3_concentration.mode_ppb, self.he3_concentration.max_ppb
        )

        # Calculate He-3 output
        throughput_kg = self.config.he3_regolith_processing_throughput_tons_per_step * 1000
        he3_output = throughput_kg * helium_concentration_ppb * 1e-9 * self.config.efficiency

        return (
            {"He3_kg": he3_output},  # Generated resources
            {},  # Consumed resources
            self.config.he3_extraction_power_kWh,  # Power consumed
        )
