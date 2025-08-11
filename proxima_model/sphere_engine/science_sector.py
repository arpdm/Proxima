"""
science_sector.py

Manages all science-related activities in the Proxima simulation.
Handles science rovers, research operations, and power management.
"""

from proxima_model.components.science_rover import ScienceRover


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
        self.throttle_factor = 1.0  # 0..1, set by WorldSystem

        self._initialize_rovers()

    def _initialize_rovers(self):
        """Initialize all science rovers from config."""

        rover_configs = self.config.get("science_rovers", [])
        for agent_config in rover_configs:
            self.metric_contributions = agent_config.get("metric_contribution")
            quantity = agent_config.get("quantity", 1)
            for _ in range(quantity):
                rover = ScienceRover(agent_config)
                self.science_rovers.append(rover)

    def set_throttle_factor(self, factor: float):
        """WorldSystem hook to throttle science operations."""
        try:
            self.throttle_factor = max(0.0, min(1.0, float(factor)))
        except Exception:
            self.throttle_factor = 1.0

    def get_power_demand(self):
        """
        Calculate total power demand from all science operations.

        Returns:
            float: Total power demand in kW
        """
        baseline_power = 2.0
        rover_power = sum(rover.battery_capacity_kWh for rover in self.science_rovers if rover.needs_charge())
        # Apply throttle to requested demand
        self.total_power_demand = (baseline_power + rover_power) * self.throttle_factor
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
        self.operational_rovers_count = 0  # Track operational rovers for metrics

        # Throttle effective usable power
        remaining_power = available_power * self.throttle_factor

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

                # Count operational rovers (those that actually used power/generated science)
                if power_used > 0 or science_generated > 0:
                    self.operational_rovers_count += 1

        # Update cumulative science
        self.total_science_cumulative += self.step_science_generated
        return self.total_power_used, self.step_science_generated

    def _create_metric_map(self):
        """
        Create a map of metric IDs and their corresponding values.
        Only contributes metrics if rovers actually operated in this step.

        Returns:
            dict: A dictionary where keys are metric IDs and values are their contributions.
        """
        metric_map = {}

        # Only calculate contributions if there are operational rovers
        if hasattr(self, "operational_rovers_count") and self.operational_rovers_count > 0:
            value = float(
                self.metric_contributions.get("value", self.metric_contributions.get("contribution_value", 0.0))
            )
            metric_id = self.metric_contributions.get("metric_id", "IND-DUST-COV")
            metric_map[metric_id] = self.operational_rovers_count * value

        return metric_map

    def get_metrics(self):
        """
        Get science sector metrics only.

        Returns:
            dict: Science metrics for logging
        """
        return {
            "science_generated": self.step_science_generated,
            "total_science_cumulative": self.total_science_cumulative,
            "operational_rovers": getattr(self, "operational_rovers_count", 0),
            "total_power_demand": self.total_power_demand,
            "metric_contributions": self._create_metric_map(),
        }
