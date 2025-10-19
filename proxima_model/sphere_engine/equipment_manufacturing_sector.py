"""
equipment_manufacturing_sector.py

PROXIMA LUNAR SIMULATION - EQUIPMENT MANUFACTURING SECTOR MANAGER

PURPOSE:
========

CORE ALGORITHMS:
===============




"""

from __future__ import annotations
from typing import Dict, List, Optional


class EquipmentManSector:
    """Manages equipment manufacturing, storage, and resupply processes."""

    def __init__(self, model, config, event_bus):
        """
        Initialize equipment manufacturing sector with agents and resource stocks.

        Args:
            model: Reference to world system model
            config: Manufacturing configuration from database
            event_bus: The central event bus for inter-sector communication.
        """
        self.model = model
        self.config = config
        self.event_bus = event_bus
        self.sector_state = "active"

        self.equipment: Dict[str, float] = config.get("initial_stocks", {})
        
        # NEW: Track items that have been ordered but have not yet arrived.
        self.pending_orders: Dict[str, float] = {}

        # Subscribe to events
        self.event_bus.subscribe("payload_delivered", self.handle_payload_delivery)

    def handle_payload_delivery(self, destination: str, payload: dict):
        """Handles incoming payloads from transport events."""
        # This sector only cares about payloads arriving at the Moon
        if destination == "Moon":
            print(f"EquipmentManSector receiving payload: {payload}")
            for item, amount in payload.items():
                # Add to physical stock
                self.equipment[item] = self.equipment.get(item, 0) + amount
                
                # NEW: Decrement the pending order count for the received item.
                if item in self.pending_orders:
                    self.pending_orders[item] = max(0, self.pending_orders.get(item, 0) - amount)

    def _check_and_request_resupply(self):
        """
        Checks effective stock (current + pending) and requests resupply if needed.
        This prevents sending duplicate requests for items already in transit.
        """
        desired_minimums = {"Assembly_Robot_EQ": 1, "Printing_Robot_EQ": 1}
        payload_to_request = {}

        for item, min_level in desired_minimums.items():
            current_stock = self.equipment.get(item, 0)
            pending_stock = self.pending_orders.get(item, 0)
            effective_stock = current_stock + pending_stock

            if effective_stock < min_level:
                # Calculate how many to order to reach the minimum
                amount_to_order = min_level - effective_stock
                payload_to_request[item] = amount_to_order
                
                # NEW: Immediately update pending orders to reflect the new request.
                self.pending_orders[item] = pending_stock + amount_to_order

        if payload_to_request:
            print(f"EquipmentManSector requesting transport for: {payload_to_request}")
            self.event_bus.publish(
                "transport_request",
                requesting_sector="equipment_manufacturing",
                payload=payload_to_request,
                origin="Moon",
                destination="Earth",
            )

    def get_power_demand(self):
        return 1

    def get_equipment(self):
        """Return current stocks (read-only copy)."""
        return self.equipment.copy()

    def step(self, allocated_power):
        """
        Checks for resupply needs at each step.
        """
        self._check_and_request_resupply()
        # This sector does not consume power directly in this version
        return allocated_power

    def get_metrics(self):
        """
        Return comprehensive manufacturing sector metrics.
        """
        metrics = {
            "sector_state": self.sector_state,
            **{f"equipment_{k}": v for k, v in self.equipment.items()},
            **{f"pending_{k}": v for k, v in self.pending_orders.items()}
        }
        return metrics