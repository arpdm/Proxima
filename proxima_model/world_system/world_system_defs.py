"""
definitions.py

PROXIMA LUNAR SIMULATION - MASTER DEFINITIONS

PURPOSE:
========
Centralized global constants, enums, and definitions used across the simulation.
Single source of truth for shared configuration and constants.
Universal definitions that are not sector-specific.
"""

from enum import Enum
from typing import Dict
from dataclasses import dataclass


# =============================================================================
# EVENT BUS EVENT TYPES
# =============================================================================


class EventType(Enum):
    """Standard event types published on the event bus."""

    # Construction events
    CONSTRUCTION_REQUEST = "construction_request"
    MODULE_COMPLETED = "module_completed"
    SHELL_PRODUCED = "shell_produced"

    # Equipment events
    EQUIPMENT_REQUEST = "equipment_request"
    EQUIPMENT_ALLOCATED = "equipment_allocated"
    EQUIPMENT_DELIVERY_CONFIRMED = "equipment_delivery_confirmed"

    # Payload/Transportation events
    PAYLOAD_DELIVERY = "payload_delivered"
    PAYLOAD_REQUEST = "payload_request"
    TRANSPORT_REQUEST = "transport_request"

    # Manufacturing
    RESOURCE_REQUEST = "resource_request"
    RESOURCE_ALLOCATED = "resource_allocated"


# =============================================================================
# SIMULATION CONSTANTS
# =============================================================================


@dataclass
class RunnerConfig:
    """Configuration for the ProximaRunner."""

    local_uri: str = "mongodb://localhost:27017"
    hosted_uri: str = None
    host_update_frequency: int = 600
    default_step_delay: float = 0.01
    log_flush_interval: int = 1000  # Flush logs every N steps to manage memory
    experiment = "exp_001"


# ===========================
class SimulationConstants:
    """Global simulation constants."""

    # Time and steps
    DEFAULT_STEP_DELAY_MS = 100
    DEFAULT_MAX_STEPS = 1000

    # Power
    DEFAULT_POWER_ALLOCATION_MODE = "proportional"
    MIN_POWER_ALLOCATION = 0.0

    # Environment
    DEFAULT_DUST_DECAY_PER_STEP = 0.0

    # Metrics
    METRIC_PRECISION_DECIMALS = 4
    SCORE_MIN = 0.0
    SCORE_MAX = 1.0


# =============================================================================
# CONSTRUCTION SECTOR
# =============================================================================


@dataclass
class AssemblyRobotConstants:

    MAX_POWER_USAGE_KWH = 50.0
    EFFICIENCY = 0.9
    ASSEMBLY_TIME_T = 60


# =============================================================================
# SECTOR DEFINITIONS
# =============================================================================


class SectorType(Enum):
    """Enumeration of all simulation sectors."""

    ENERGY = "energy"
    SCIENCE = "science"
    MANUFACTURING = "manufacturing"
    EQUIPMENT_MANUFACTURING = "equipment_manufacturing"
    TRANSPORTATION = "transportation"
    CONSTRUCTION = "construction"
    ENVIRONMENT = "environment"
    PERFORMANCE = "performance"


# =============================================================================
# MODULE AND EQUIPMENT DEFINITIONS
# =============================================================================


class ModuleType(Enum):
    """Types of modules that can be constructed."""

    SCIENCE_ROVER = "science_rover"
    ENERGY_GENERATOR = "energy_generator"
    HABITATION_MODULE = "habitation_module"
    ISRU_ROBOT = "isru_robot"
    ROCKET = "rocket"
    PRINTING_ROBOT = "printing_robot"
    ASSEMBLY_ROBOT = "assembly_robot"


class EquipmentType(Enum):
    """Types of equipment used in construction."""

    SCIENCE_ROVER_EQ = "Science_Rover_EQ"
    ENERGY_GENERATOR_EQ = "Energy_Generator_EQ"
    HABITATION_MODULE_EQ = "Habitation_Module_EQ"
    ISRU_ROBOT_EQ = "ISRU_Robot_EQ"
    ROCKET_EQ = "Rocket_EQ"
    PRINTING_ROBOT_EQ = "Printing_Robot_EQ"
    ASSEMBLY_ROBOT_EQ = "Assembly_Robot_EQ"


# Module ID to Equipment Type mapping
MODULE_TO_EQUIPMENT_MAP: Dict[str, str] = {
    "comp_science_rover": EquipmentType.SCIENCE_ROVER_EQ.value,
    "comp_energy_generator": EquipmentType.ENERGY_GENERATOR_EQ.value,
    "comp_habitation_module": EquipmentType.HABITATION_MODULE_EQ.value,
    "comp_isru_robot": EquipmentType.ISRU_ROBOT_EQ.value,
    "comp_rocket": EquipmentType.ROCKET_EQ.value,
    "comp_printing_robot": EquipmentType.PRINTING_ROBOT_EQ.value,
    "comp_assembly_robot": EquipmentType.ASSEMBLY_ROBOT_EQ.value,
}

# Module ID to Module Type mapping
MODULE_ID_TO_TYPE_MAP: Dict[str, ModuleType] = {
    "comp_science_rover": ModuleType.SCIENCE_ROVER,
    "comp_energy_generator": ModuleType.ENERGY_GENERATOR,
    "comp_habitation_module": ModuleType.HABITATION_MODULE,
    "comp_isru_robot": ModuleType.ISRU_ROBOT,
    "comp_rocket": ModuleType.ROCKET,
    "comp_printing_robot": ModuleType.PRINTING_ROBOT,
    "comp_assembly_robot": ModuleType.ASSEMBLY_ROBOT,
}

# Module Type to Sector mapping (which sector receives this module)
MODULE_TYPE_TO_SECTOR_MAP: Dict[ModuleType, SectorType] = {
    ModuleType.SCIENCE_ROVER: SectorType.SCIENCE,
    ModuleType.ENERGY_GENERATOR: SectorType.ENERGY,
    ModuleType.HABITATION_MODULE: SectorType.CONSTRUCTION,
    ModuleType.ISRU_ROBOT: SectorType.MANUFACTURING,
    ModuleType.ROCKET: SectorType.TRANSPORTATION,
    ModuleType.PRINTING_ROBOT: SectorType.CONSTRUCTION,
    ModuleType.ASSEMBLY_ROBOT: SectorType.CONSTRUCTION,
}

# =============================================================================
# METRIC DEFINITIONS
# =============================================================================


class MetricCategory(Enum):
    """Categories for grouping metrics."""

    ENERGY = "energy"
    SCIENCE = "science"
    MANUFACTURING = "manufacturing"
    CONSTRUCTION = "construction"
    TRANSPORTATION = "transportation"
    ENVIRONMENT = "environment"
    PERFORMANCE = "performance"
    RESOURCES = "resources"


# =============================================================================
# ALLOCATION MODES
# =============================================================================


class AllocationMode(Enum):
    """Power allocation strategies."""

    PROPORTIONAL = "proportional"
    EQUAL = "equal"
    PRIORITY = "priority"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_equipment_type_for_module(module_id: str) -> str:
    """Get equipment type string for a module ID."""
    return MODULE_TO_EQUIPMENT_MAP.get(module_id, "")


def get_module_type_for_id(module_id: str) -> ModuleType:
    """Get module type enum for a module ID."""
    return MODULE_ID_TO_TYPE_MAP.get(module_id)


def get_target_sector_for_module(module_type: ModuleType) -> SectorType:
    """Get the sector that should receive a completed module."""
    return MODULE_TYPE_TO_SECTOR_MAP.get(module_type)


def extract_module_type_from_id(module_id: str) -> str:
    """Extract module type string from module_id (e.g., 'comp_science_rover' -> 'science_rover')."""
    return module_id.replace("comp_", "")


def get_sector_list() -> list:
    """Return a list of available sectors as SectorType enum members."""
    return [s.value for s in SectorType]
