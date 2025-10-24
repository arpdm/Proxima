"""
equipment_manufacturing_sector.py

PROXIMA LUNAR SIMULATION - EQUIPMENT MANUFACTURING SECTOR MANAGER

PURPOSE:
========
Manages equipment manufacturing, storage, and resupply processes.
Tracks physical stock and pending orders to prevent duplicate resupply requests.

CORE ALGORITHMS:
===============
1) Monitor equipment levels against minimum thresholds
2) Calculate effective stock (physical + pending orders)
3) Request resupply only when effective stock falls below minimum
4) Update inventory when payloads arrive from Earth
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


class SectorState(Enum):
    """Equipment manufacturing sector operational states."""

    ACTIVE = auto()
    INACTIVE = auto()


class EquipmentType(Enum):
    """Available equipment types for expansion."""

    ASSEMBLY_ROBOT = "Assembly_Robot_EQ"
    PRINTING_ROBOT = "Printing_Robot_EQ"
    # Add more equipment types as needed


@dataclass
class EquipmentConfig:
    """Configuration for equipment minimum levels."""

    minimum_level: int = 1

    def __post_init__(self):
        if self.minimum_level < 0:
            raise ValueError("Minimum level must be non-negative")


@dataclass
class EquipmentInventory:
    """Manages equipment stock levels."""

    physical_stock: Dict[str, float] = field(default_factory=dict)
    pending_orders: Dict[str, float] = field(default_factory=dict)

    def get_physical(self, item: str) -> float:
        """Get physical stock for an item."""
        return self.physical_stock.get(item, 0)

    def get_pending(self, item: str) -> float:
        """Get pending orders for an item."""
        return self.pending_orders.get(item, 0)

    def get_effective(self, item: str) -> float:
        """Get effective stock (physical + pending)."""
        return self.get_physical(item) + self.get_pending(item)

    def add_physical(self, item: str, amount: float):
        """Add to physical stock."""
        if amount < 0:
            raise ValueError("Amount must be non-negative")
        self.physical_stock[item] = self.get_physical(item) + amount

    def add_pending(self, item: str, amount: float):
        """Add to pending orders."""
        if amount < 0:
            raise ValueError("Amount must be non-negative")
        self.pending_orders[item] = self.get_pending(item) + amount

    def reduce_pending(self, item: str, amount: float):
        """Reduce pending orders (on delivery)."""
        if amount < 0:
            raise ValueError("Amount must be non-negative")
        self.pending_orders[item] = max(0, self.get_pending(item) - amount)


class EquipmentManSector:
    """Manages equipment manufacturing, storage, and resupply processes."""

    # Default minimum levels for equipment
    DEFAULT_MINIMUMS = {
        EquipmentType.ASSEMBLY_ROBOT.value: 1,
        EquipmentType.PRINTING_ROBOT.value: 1,
    }

    def __init__(self, model, config: Dict, event_bus):
        """
        Initialize equipment manufacturing sector with agents and resource stocks.

        Args:
            model: Reference to world system model
            config: Manufacturing configuration from database
            event_bus: The central event bus for inter-sector communication
        """
        self.model = model
        self.config = config
        self.event_bus = event_bus
        self.sector_state = SectorState.ACTIVE

        # Buffer for incoming events (process next step)
        self._event_buffer = []

        # Initialize inventory
        initial_stocks = config.get("initial_stocks", {})
        self._inventory = EquipmentInventory(physical_stock=initial_stocks.copy(), pending_orders={})

        # Load minimum levels (allow config overrides)
        self._minimum_levels = {**self.DEFAULT_MINIMUMS, **config.get("minimum_levels", {})}

        # Subscribe to events
        self.event_bus.subscribe("payload_delivered", self.handle_payload_delivery)

    @property
    def equipment(self) -> Dict[str, float]:
        """Get physical equipment stock (for backwards compatibility)."""
        return self._inventory.physical_stock.copy()

    @property
    def pending_orders(self) -> Dict[str, float]:
        """Get pending orders (for backwards compatibility)."""
        return self._inventory.pending_orders.copy()

    def handle_payload_delivery(self, to_sector: str, payload: Dict[str, float]):
        """Buffer payload delivery events to process next step."""
        if to_sector == self.config.get("sector_name"):
            # Buffer the event instead of processing immediately
            self._event_buffer.append(("payload_delivered", payload))

    def _process_buffered_events(self):
        # Process in reverse order (LIFO - most recent first)
        for event_type, payload in reversed(self._event_buffer):
            if event_type == "payload_delivered":
                logger.info(f"Equipment Manufacturing Sector Processing Buffered Payload: {payload}")
                for item, amount in payload.items():
                    self._inventory.add_physical(item, amount)
                    self._inventory.reduce_pending(item, amount)
                self._event_buffer.clear()

    def _check_and_request_resupply(self):
        """
        Check effective stock (current + pending) and request resupply if needed.

        This prevents sending duplicate requests for items already in transit
        by considering both physical stock and pending orders.
        """
        payload_to_request = {}

        for item, min_level in self._minimum_levels.items():
            effective_stock = self._inventory.get_effective(item)

            if effective_stock < min_level:
                # Calculate how many to order to reach the minimum
                amount_to_order = min_level - effective_stock
                payload_to_request[item] = amount_to_order

                # Update pending orders to reflect the new request
                self._inventory.add_pending(item, amount_to_order)

        if payload_to_request:
            logger.info(f"EquipmentManSector requesting transport for: {payload_to_request}")
            self.event_bus.publish(
                "transport_request",
                requesting_sector="equipment_manufacturing",
                payload=payload_to_request,
                origin="Moon",  # TODO: Get from Environment Configuration
                destination="Earth",  # TODO: Get from Environment Configuration
            )

    def get_power_demand(self) -> float:
        """
        Calculate power demand for equipment manufacturing.

        Returns:
            Power demand in kW (currently fixed at 1.0)
        """
        return 1.0

    def get_equipment(self) -> Dict[str, float]:
        """
        Return current physical equipment stocks (read-only copy).

        Returns:
            Dictionary of equipment items and quantities
        """
        return self.equipment

    def step(self, allocated_power: float) -> float:
        """
        Execute single simulation step for equipment manufacturing sector.

        Checks for resupply needs and requests transport as needed.

        Args:
            allocated_power: Power allocated to sector (currently unused)

        Returns:
            Remaining power (unchanged as sector doesn't consume power yet)
        """

        self._process_buffered_events()
        self._check_and_request_resupply()
        # This sector does not consume power directly in this version
        return allocated_power

    def get_metrics(self) -> Dict:
        """
        Return comprehensive equipment manufacturing sector metrics.

        Returns:
            Dictionary containing sector state, physical stock, and pending orders
        """
        return {
            "sector_state": self.sector_state.name,
            **{f"equipment_{k}": v for k, v in self._inventory.physical_stock.items()},
        }
