"""
Assembly Robot Component
Handles assembly of world system modules from structural shells and equipment
"""

from mesa import Agent
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AssemblyRobotMode(Enum):
    """Assembly robot operational modes."""

    IDLE = "idle"
    ASSEMBLING = "assembling"


class AssemblyRobot(Agent):
    """
    Assembly robot that assembles modules from shells.
    """

    def __init__(self, model, config: dict):
        super().__init__(model)
        self.config = config

        # Characteristics
        self.max_power_usage_kWh = float(config.get("max_power_usage_kWh", 50.0))
        self.efficiency = float(config.get("efficiency", 0.9))
        self.assembly_time_steps = int(config.get("assembly_time_t", 60))

        # State
        self.mode = AssemblyRobotMode.IDLE
        self.assembly_steps_remaining = 0
        self.current_module = None

        # Metrics
        self.modules_assembled = 0

    def start_assembly(self, module_type: str) -> bool:
        """Start assembling a module if idle."""
        if self.mode != AssemblyRobotMode.IDLE:
            return False

        self.mode = AssemblyRobotMode.ASSEMBLING
        self.assembly_steps_remaining = self.assembly_time_steps
        self.current_module = module_type

        logger.debug(f"Assembly robot {self.unique_id} started assembling {module_type}")
        return True

    def get_power_demand(self) -> float:
        """Get current power demand."""
        return self.max_power_usage_kWh if self.mode == AssemblyRobotMode.ASSEMBLING else 0.0

    def step(self) -> dict:
        """Execute one simulation step."""
        result = {"module_completed": None}

        if self.mode == AssemblyRobotMode.ASSEMBLING:
            self.assembly_steps_remaining -= 1

            if self.assembly_steps_remaining <= 0:
                # Assembly complete
                result["module_completed"] = self.current_module
                self.modules_assembled += 1

                # Reset to idle
                self.mode = AssemblyRobotMode.IDLE
                self.current_module = None
                self.assembly_steps_remaining = 0

                logger.debug(f"Assembly robot {self.unique_id} completed module assembly")

        return result

    def report(self) -> dict:
        """Return status report."""
        return {
            "type": "assembly_robot",
            "mode": self.mode.value,
            "assembly_remaining": self.assembly_steps_remaining,
            "modules_assembled": self.modules_assembled,
            "power_demand": self.get_power_demand(),
        }
