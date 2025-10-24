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


class ExtractionMode(Enum):
    """Available extraction modes for ISRU operations."""

    ICE = "ICE"
    REGOLITH = "REGOLITH"
    INACTIVE = "INACTIVE"


class GenerationMode(Enum):
    """Available generation modes for ISRU operations."""

    HE3 = "HE3"
    INACTIVE = "INACTIVE"


@dataclass
class ExtractorConfig:
    """Configuration for ISRU Extractor agents."""

    max_power_usage_kWh: float = 15.0
    ice_extraction_power_kWh: float = 5.0
    ice_extraction_output_kg: float = 20.0
    regolith_extraction_power_kWh: float = 10.0
    regolith_extraction_output_kg: float = 100.0
    efficiency: float = 0.9
    processing_time_t: int = 3
    extraction_modes: List[str] = field(default_factory=lambda: ["ICE", "REGOLITH", "INACTIVE"])

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not (0 < self.efficiency <= 1):
            raise ValueError(f"Efficiency must be between 0 and 1, got {self.efficiency}")
        if self.processing_time_t < 0:
            raise ValueError("Processing time must be non-negative")


@dataclass
class GeneratorConfig:
    """Configuration for ISRU Generator agents."""

    max_power_usage_kWh: float = 65.0
    he3_extraction_power_kWh: float = 50.0
    he3_regolith_processing_throughput_tons_per_step: float = 100.0
    efficiency: float = 0.85
    generator_modes: List[str] = field(default_factory=lambda: ["HE3", "INACTIVE"])
    regolith_required_per_operation_kg: float = 100000.0  # 100 tons

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not (0 < self.efficiency <= 1):
            raise ValueError(f"Efficiency must be between 0 and 1, got {self.efficiency}")


@dataclass
class He3Concentration:
    """He-3 concentration parameters."""

    min_ppb: float
    max_ppb: float
    mode_ppb: float = field(init=False)

    def __post_init__(self):
        self.mode_ppb = (self.min_ppb + self.max_ppb) / 2


class ISRUExtractor(Agent):
    """ISRU Extraction Agent - handles ice and regolith extraction."""

    def __init__(self, model, config: dict):
        super().__init__(model)

        # Create configuration dataclass from dict
        self.config = ExtractorConfig(**{k: v for k, v in config.items() if k in ExtractorConfig.__dataclass_fields__})

        # Agent identification
        self.agent_type = "isru"
        self.subtype = "extractor"

        # Operational state
        self._processing_time = self.config.processing_time_t
        try:
            self.operational_mode = ExtractionMode(self.config.extraction_modes[0])
        except (ValueError, IndexError):
            self.operational_mode = ExtractionMode.ICE

        # Cache power demands for efficiency
        self._power_demand_cache = {
            ExtractionMode.ICE: self.config.ice_extraction_power_kWh,
            ExtractionMode.REGOLITH: self.config.regolith_extraction_power_kWh,
            ExtractionMode.INACTIVE: 0.0,
        }

    def set_operational_mode(self, mode: str) -> None:
        """Set the operational mode for this extractor."""
        try:
            self.operational_mode = ExtractionMode(mode)
        except ValueError:
            available_modes = [mode.value for mode in ExtractionMode]
            logger.error(f"Invalid mode {mode}. Available modes: {available_modes}")

    def get_power_demand(self) -> float:
        """Return current power demand based on operational mode."""
        return self._power_demand_cache[self.operational_mode]

    def extract_resources(self, allocated_power: float) -> Tuple[Dict[str, float], float]:
        """Perform actual extraction operations with allocated power."""

        power_needed = self.get_power_demand()

        # Check if we have enough power to operate
        if allocated_power < power_needed:
            return {}, 0.0

        # Decrement processing time
        if self._processing_time > 0:
            self._processing_time -= 1
            return {}, power_needed  # Still processing - no output yet

        # Processing complete - generate output and reset timer
        extracted_resources = self._generate_output()
        self._processing_time = self.config.processing_time_t

        return extracted_resources, power_needed

    def _generate_output(self) -> Dict[str, float]:
        """Generate output based on current operational mode."""
        if self.operational_mode == ExtractionMode.ICE:
            output = self.config.ice_extraction_output_kg * self.config.efficiency
            return {"H2O_kg": output}
        elif self.operational_mode == ExtractionMode.REGOLITH:
            output = self.config.regolith_extraction_output_kg * self.config.efficiency
            return {"FeTiO3_kg": output}
        return {}


class ISRUGenerator(Agent):
    """ISRU Generation Agent - handles He-3 extraction and other resource generation."""

    def __init__(self, model, config: dict):
        super().__init__(model)

        # Create configuration dataclass from dict
        self.config = GeneratorConfig(**{k: v for k, v in config.items() if k in GeneratorConfig.__dataclass_fields__})

        # Agent identification
        self.agent_type = "isru"
        self.subtype = "generator"

        # Setup He-3 concentration parameters from environment
        self.he3_concentration = self._setup_he3_parameters(model)

        # Operational state
        try:
            self.operational_mode = GenerationMode(self.config.generator_modes[0])
        except (ValueError, IndexError):
            self.operational_mode = GenerationMode.INACTIVE

        # Cache power demands for efficiency
        self._power_demand_cache = {
            GenerationMode.HE3: self.config.he3_extraction_power_kWh,
            GenerationMode.INACTIVE: 0.0,
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
        """Set the operational mode for this generator."""
        try:
            self.operational_mode = GenerationMode(mode)
        except ValueError:
            available_modes = [mode.value for mode in GenerationMode]
            logger.error(f"Invalid mode {mode}. Available modes: {available_modes}")

    def get_power_demand(self) -> float:
        """Return current power demand based on operational mode."""
        return self._power_demand_cache[self.operational_mode]

    def generate_resources(
        self, allocated_power: float, stocks: Dict[str, float]
    ) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """Perform generation operations based on operational mode."""

        power_needed = self.get_power_demand()

        # Check if we have enough power to operate
        if allocated_power < power_needed:
            return {}, {}, 0.0

        # Route to appropriate generation method based on mode
        if self.operational_mode == GenerationMode.HE3:
            return self._generate_he3()
        elif self.operational_mode == GenerationMode.INACTIVE:
            return self._generate_inactive()

        return {}, {}, 0.0

    def _generate_he3(self) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """Generation logic for HE3 mode with proper regolith consumption."""

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

    def _generate_inactive(self) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """No operation for INACTIVE mode."""
        return {}, {}, 0.0
