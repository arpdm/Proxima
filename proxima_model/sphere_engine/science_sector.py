"""
science_sector.py

Manages all science-related activities in the Proxima simulation.
Handles science rovers, research operations, and power management.
"""

from proxima_model.components.sceince_rover import ScienceRover


class ScienceSector:
    """Manages science rovers and research operations."""

    def __init__(self, config):
        """
        Initialize the science sector.

        Args:
            config (dict): Science sector configuration including rover specs
        """
        self.config = config
        self.science_rovers = []
        self.total_science_cumulative = 0.0
        self.step_science_generated = 0.0
        self.total_power_demand = 0.0
        self.total_power_used = 0.0

        self._initialize_rovers()

    def _initialize_rovers(self):
        """Initialize all science rovers from config."""
        rover_configs = self.config.get("science_rovers", [])
        for agent_config in rover_configs:
            quantity = agent_config.get("quantity", 1)
            for _ in range(quantity):
                rover = ScienceRover(agent_config)
                self.science_rovers.append(rover)

    def get_power_demand(self):
        """
        Calculate total power demand from all science operations.

        Returns:
            float: Total power demand in kW
        """
        baseline_power = 2.0  # Base science operations
        rover_power = sum(rover.battery_capacity_kWh for rover in self.science_rovers if rover.needs_charge())
        self.total_power_demand = baseline_power + rover_power
        return self.total_power_demand

    def step(self, available_power):
        """
        Execute one simulation step for the science sector.

        Args:
            available_power (float): Available power from microgrid in kW

        Returns:
            tuple: (power_used, science_generated)
        """
        self.step_science_generated = 0.0
        self.total_power_used = 0.0
        remaining_power = available_power

        # Update each rover
        for rover in self.science_rovers:
            if remaining_power <= 0:
                # No power available
                rover.status = "waiting_for_power"
                rover.is_operational = False
            else:
                # Rover operates with available power
                power_used, science_generated = rover.step(remaining_power)
                remaining_power = max(0.0, remaining_power - power_used)
                self.total_power_used += power_used
                self.step_science_generated += science_generated

        # Update cumulative science
        self.total_science_cumulative += self.step_science_generated
        return self.total_power_used, self.step_science_generated

    def get_metrics(self):
        """
        Get science sector metrics only.

        Returns:
            dict: Science metrics for logging
        """
        return {
            "science_generated": self.step_science_generated,
            "total_science_cumulative": self.total_science_cumulative,
            "operational_rovers": sum(1 for rover in self.science_rovers if rover.is_operational),
            "total_power_demand": self.total_power_demand,
        }
