"""
Printing Robot Component

Handles 3D printing of structural shells for lunar base construction.
"""

from mesa import Agent
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class PrintingRobotMode(Enum):
    """Printing robot operational modes."""

    IDLE = "idle"
    PRINTING = "printing"


class PrintingRobot(Agent):
    """
    Printing robot that consumes regolith to produce structural shells.
    """

    def __init__(self, model, config: dict):
        super().__init__(model)
        self.config = config

        # Characteristics
        self.max_power_usage_kWh = float(config.get("max_power_usage_kWh", 65.0))
        self.efficiency = float(config.get("efficiency", 0.9))
        self.processing_time_steps = int(config.get("processing_time_t", 80))
        self.regolith_usage_kg = float(config.get("regolith_usage_kg", 200.0))

        # State
        self.mode = PrintingRobotMode.IDLE
        self.processing_steps_remaining = 0

        # Metrics
        self.shells_produced = 0

    def start_printing(self, shell_type: str = "standard") -> bool:
        """
        Start printing a shell if idle.

        Args:
            shell_type: Type of shell to print

        Returns:
            True if printing started, False if busy
        """
        if self.mode != PrintingRobotMode.IDLE:
            return False

        self.mode = PrintingRobotMode.PRINTING
        self.processing_steps_remaining = self.processing_time_steps

        logger.debug(f"Printing robot {self.unique_id} started printing {shell_type}")
        return True

    def get_power_demand(self) -> float:
        """Get current power demand."""
        return self.max_power_usage_kWh if self.mode == PrintingRobotMode.PRINTING else 0.0

    def step(self) -> dict:
        """
        Execute one simulation step.

        Returns:
            Dict with production results
        """
        result = {"shell_produced": None, "regolith_consumed": 0.0}

        if self.mode == PrintingRobotMode.PRINTING:
            self.processing_steps_remaining -= 1

            if self.processing_steps_remaining <= 0:
                # Production complete
                result["shell_produced"] = 1
                result["regolith_consumed"] = self.regolith_usage_kg
                self.shells_produced += 1

                # Reset to idle
                self.mode = PrintingRobotMode.IDLE
                self.processing_steps_remaining = 0

                logger.debug(f"Printing robot {self.unique_id} completed shell production")

        return result

    def report(self) -> dict:
        """Return status report."""
        return {
            "type": "printing_robot",
            "mode": self.mode.value,
            "processing_remaining": self.processing_steps_remaining,
            "shells_produced": self.shells_produced,
            "power_demand": self.get_power_demand(),
        }
