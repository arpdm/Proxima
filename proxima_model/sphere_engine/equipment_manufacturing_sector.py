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
    """Manages equipment manufacturing and storage processes."""

    def __init__(self, model, config):
        """
        Initialize equipment manufacturing sector with agents and resource stocks.

        Args:
            model: Reference to world system model
            config: Manufacturing configuration from database
        """
        self.model = model
        self.config = config
        self.sector_state = "active"

        self.pending_stock_flows: List[Dict[str, Dict[str, float]]] = []
        self.equipment: Dict[str, float] = config.get(
            "initial_stocks",
            {
                "Solar_Array_EQ": 0, 
                "ISRU_Generator_EQ": 0,
                "ISRU_Extractor_EQ": 0, 
                "Assembly_Robot_EQ": 0, 
                "Printing_Robot_EQ": 0
            }
        )

    def get_equpment(self):
        """Return current stocks (read-only copy)."""
        return self.equipment.copy()

    def add_stock_flow(self, source_component: str,
                       consumed: Optional[Dict[str, float]] = None,
                       generated: Optional[Dict[str, float]] = None) -> None:
        """
        Add a stock flow transaction to pending queue.

        Stock flows are batched and processed atomically to prevent
        race conditions and ensure resource conservation.

        Args:
            source_component: Component generating the flow
            consumed_resources: Resources consumed (optional)
            generated_resources: Resources generated (optional)
        """
        self.pending_stock_flows.append(
            {
                "source": source_component,
                "consumed": consumed or {},
                "generated": generated or {},
            }
        )

    def process_all_stock_flows(self):
        """
        Process all pending stock flows atomically.

        Ensures resource conservation by applying all consumption
        and generation transactions in a single batch operation.

        Returns:
            dict: Summary of total consumed and generated resources
        """
        if not self.pending_stock_flows:
            return {}

        total_consumed = {}
        total_generated = {}

        # Process all flows atomically
        for flow in self.pending_stock_flows:
            # Apply consumption
            for resource, amount in flow["consumed"].items():
                if resource in self.equipment:
                    self.equipment[resource] = max(0, self.equipment[resource] - amount)
                    total_consumed[resource] = total_consumed.get(resource, 0) + amount

            # Apply generation
            for resource, amount in flow["generated"].items():
                self.equipment[resource] = self.equipment.get(resource, 0) + amount
                total_generated[resource] = total_generated.get(resource, 0) + amount

        self.pending_stock_flows = []
        return {"consumed": total_consumed, "generated": total_generated}


    def step(self, allocated_power):
        """
        Execute a manufacturing of materials based on bffer-based policy

        EXECUTION SEQUENCE:
        1) Process all stock flows

        Args:
            allocated_power: Power budget allocated by world system

        Returns:
            float: Unused power returned to world system
        """
        self.process_all_stock_flows()

    def get_metrics(self):
        """
        Return comprehensive manufacturing sector metrics including DRR token tracking.

        Returns:
            dict: Manufacturing sector performance metrics
        """
        return {
            "sector_state": self.sector_state,
            **{f"equipment_{k}": v for k, v in self.equipment.items()}
        }