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
from typing import Any, Dict
from collections import deque

import logging

logger = logging.getLogger(__name__)


class SectorState(Enum):
    """Equipment manufacturing sector operational states."""

    ACTIVE = auto()
    INACTIVE = auto()

#TODO: Move to the definitions
class EquipmentType(Enum):
    """Available equipment types for expansion."""

    ASSEMBLY_ROBOT = "Assembly_Robot_EQ"
    PRINTING_ROBOT = "Printing_Robot_EQ"
    SCIENCE_ROVER = "Science_Rover_EQ"
    ENERGY_GENERATOR = "Energy_Generator_EQ"
    ISRU_ROBOT = "ISRU_Robot_EQ"
    ROCKET = "Rocket_EQ"


@dataclass
class EquipmentConfig:
    """Configuration for equipment minimum levels."""

    minimum_level: int = 3

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

    def remove(self, item: str, amount: float):
        """Remove from physical stock (allocation to other sectors)."""
        if amount < 0:
            raise ValueError("Amount must be non-negative")

        current = self.get_physical(item)
        new_level = max(0, current - amount)
        self.physical_stock[item] = new_level

        # Keep the item in the dictionary even if it reaches 0
        # This ensures consistent metrics reporting


class EquipmentManSector:
    """Manages equipment manufacturing, storage, and resupply processes."""

    # Default minimum levels for equipment
    DEFAULT_MINIMUMS = {
        EquipmentType.ASSEMBLY_ROBOT.value: 1,
        EquipmentType.PRINTING_ROBOT.value: 1,
        EquipmentType.SCIENCE_ROVER.value: 1,
    }

    def __init__(self, model, config: Dict[str, Any], event_bus):
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
        self._equipment_backlog: deque[dict] = deque()

        # Initialize inventory
        initial_stocks = config.get("initial_stocks", {})
        self._inventory = EquipmentInventory(physical_stock=initial_stocks.copy(), pending_orders={})

        # Load minimum levels (allow config overrides)
        self._minimum_levels = {**self.DEFAULT_MINIMUMS, **config.get("minimum_levels", {})}

        # Subscribe to events
        self.event_bus.subscribe("payload_delivered", self.handle_payload_delivery)

        # Subscribe to equipment requests from other sectors
        self.event_bus.subscribe("equipment_request", self.handle_equipment_request)

    @property
    def equipment(self) -> Dict[str, float]:
        """Get physical equipment stock (for backwards compatibility)."""
        return self._inventory.physical_stock.copy()

    @property
    def pending_orders(self) -> Dict[str, float]:
        """Get pending orders (for backwards compatibility)."""
        return self._inventory.pending_orders.copy()

    def handle_payload_delivery(self, to_sector: str, payload: Dict[str, float]):
        if to_sector == self.config.get("sector_name"):
            self._event_buffer.append(("payload_delivered", payload))

    def handle_equipment_request(self, requesting_sector: str, equipment_type: str, quantity: int) -> None:
        self._event_buffer.append(
            (
                "equipment_request",
                {
                    "requesting_sector": requesting_sector,
                    "equipment_type": equipment_type,
                    "quantity": quantity,
                },
            )
        )

    def _process_buffered_events(self):
        while self._event_buffer:
            event_type, data = self._event_buffer.pop()
            if event_type == "payload_delivered":
                self._process_payload_delivery(data)
            elif event_type == "equipment_request":
                self._enqueue_equipment_request(data)

        self._process_equipment_backlog()

    def _process_payload_delivery(self, payload: Dict[str, float]) -> None:
        logger.info(f"EquipmentManSector processing payload: {payload}")
        for item, amount in payload.items():
            self._inventory.add_physical(item, amount)
            self._inventory.reduce_pending(item, amount)

    def _enqueue_equipment_request(self, payload: dict) -> None:
        self._equipment_backlog.append(payload)

    def _process_equipment_backlog(self) -> None:
        remaining_requests = deque()

        while self._equipment_backlog:
            request = self._equipment_backlog.popleft()
            outstanding = self._fulfill_equipment_request(request)

            if outstanding > 0:
                request["quantity"] = outstanding
                remaining_requests.append(request)

        self._equipment_backlog = remaining_requests

    def _fulfill_equipment_request(self, request: dict) -> int:
        "Try to fullifill the request if not, keep it in the backlog"

        requesting_sector = request["requesting_sector"]
        equipment_type = request["equipment_type"]
        quantity = request["quantity"]
        available = self._inventory.get_physical(equipment_type)

        if available >= quantity:
            self.event_bus.publish(
                "equipment_allocated",
                recipient_sector=requesting_sector,
                equipment_type=equipment_type,
                quantity=quantity,
            )
            self._inventory.remove(equipment_type, quantity)
            logger.info(f"Allocated {quantity} {equipment_type} to {requesting_sector}")
            return 0
        else:
            return quantity - available

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
