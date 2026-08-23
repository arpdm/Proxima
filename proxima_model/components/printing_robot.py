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
        self.config = config.get("config")

        # Characteristics
        self.max_power_usage_step = float(self.config.get("max_power_usage_kWh", 65.0)) * model.time_scale
        self.efficiency = float(self.config.get("efficiency", 0.9))
        self.processing_time_steps = int(self.config.get("processing_time_h", 80) / model.time_scale)
        self.regolith_usage_kg = float(self.config.get("regolith_usage_kg", 200.0))

        # State
        self.mode = PrintingRobotMode.IDLE
        self.processing_steps_remaining = 0
        self.is_throttled = False

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
        return self.max_power_usage_step if self.mode == PrintingRobotMode.PRINTING else 0.0

    def step(self, available_power: float = None) -> dict:
        """
        Execute one simulation step.

        Returns:
            Dict with production results
        """
        result = {"shell_produced": None, "regolith_consumed": 0.0, "power_used": 0.0, "throttled": False}
        self.is_throttled = False

        if self.mode == PrintingRobotMode.PRINTING:
            power_needed = self.get_power_demand()
            if available_power is not None and available_power < power_needed:
                self.is_throttled = True
                result["throttled"] = True
                return result

            result["power_used"] = power_needed
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
            "is_throttled": self.is_throttled,
        }
