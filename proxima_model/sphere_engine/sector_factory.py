"""
Sector Factory

Provides a centralized factory for creating sector instances dynamically.
"""

from typing import Any, Dict
import logging

from .science_sector import ScienceSector
from .energy_sector import EnergySector
from .transportation_sector import TransportationSector
from .construction_sector import ConstructionSector
from .manufacturing_sector import ManufacturingSector
from .equipment_manufacturing_sector import EquipmentManSector

logger = logging.getLogger(__name__)


class SectorFactory:
    """
    Factory class for creating sector instances.

    Supports dynamic instantiation based on sector type, with built-in
    validation and logging.
    """

    @staticmethod
    def create_sector(sector_type: str, model, config: Dict[str, Any], event_bus) -> Any:
        """
        Create and return a sector instance based on the sector type.

        Args:
            sector_type: The type of sector to create (e.g., "science").
            model: The Mesa model instance.
            config: Sector-specific configuration dictionary.
            event_bus: The event bus for inter-sector communication.

        Returns:
            An instance of the appropriate sector class.

        Raises:
            ValueError: If the sector type is unknown or invalid.
        """
        sector_type = sector_type.lower().strip()

        try:
            if sector_type == "science":
                return ScienceSector(model, config, event_bus)
            elif sector_type == "energy":
                return EnergySector(model, config, event_bus)
            elif sector_type == "transportation":
                return TransportationSector(model, config, event_bus)
            elif sector_type == "construction":
                return ConstructionSector(model, config, event_bus)
            elif sector_type == "manufacturing":
                return ManufacturingSector(model, config, event_bus)
            elif sector_type == "equipment_manufacturing":
                return EquipmentManSector(model, config, event_bus)
            else:
                raise ValueError(f"Unknown sector type: {sector_type}")
        except Exception as e:
            logger.error(f"Failed to create sector '{sector_type}': {e}")
            raise
