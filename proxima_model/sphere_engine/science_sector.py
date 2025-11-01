"""
science_sector.py

Manages all science-related activities in the Proxima simulation.
Handles science rovers, research operations, and power management.
"""

from proxima_model.components.science_rover import ScienceRover, RoverStatus

import random
import logging

logger_science = logging.getLogger(__name__)


class ScienceSector:
    """Manages science rovers and research operations."""

    def __init__(self, model, config, event_bus):
        """
        Initialize the science sector.

        Args:
            model: The world system model instance.
            config (dict): Science sector configuration including rover specs.
            event_bus: The simulation's central event bus.
        """

        self.model = model
        self.config = config
        self.event_bus = event_bus
        self.science_rovers = []
        self.total_science_cumulative = 0.0
        self.throttle_factor = 0.0  # 0.0 = no throttling, 1.0 = always throttled

        # Event Subscribtions
        self.event_bus.subscribe("module_completed", self.handle_module_completed)
        self._initialize_rovers()

    def _initialize_rovers(self):
        """Initialize all science rovers from config."""

        self.rover_configs = self.config.get("science_rovers", [])
        self.rover_id_counter = 0

        for agent_config in self.rover_configs:
            quantity = agent_config.get("quantity", 1)
            for _ in range(quantity):
                self._create_rover(agent_config)

    def _create_rover(self, rover_config):
        """Create a single science rover."""

        unique_id = f"science_rover_{self.rover_id_counter}"
        rover = ScienceRover(unique_id, self.model, rover_config)
        self.science_rovers.append(rover)
        self.rover_id_counter += 1
        logger_science.info(f"Created {unique_id}")
        return rover

    def handle_module_completed(self, requesting_sphere: str, module_id: str, **kwargs):
        """Handle newly constructed modules."""

        # Only process if it's for us and it's a science rover
        if requesting_sphere != self.config.get("sector_name"):
            return

        if module_id != "comp_science_rover":
            return

        # Get base config from our existing rovers
        if not self.rover_configs:
            logger_science.error("Cannot add rover: no config available")
            return

        base_config = self.rover_configs[0]
        new_rover = self._create_rover(base_config)

        logger_science.info(
            f"✅ Added new science rover: {new_rover.unique_id} " f"(total: {len(self.science_rovers)})"
        )

    def set_throttle_factor(self, throttle_value: float):
        """Set throttle factor for probabilistic rover operation (0.0 to 1.0)."""

        self.throttle_factor = max(0.0, min(1.0, throttle_value))  # Clamp to 0-1

    def get_power_demand(self) -> float:
        """
        Calculate total power demand from all rovers that need to charge.
        A rover needs to charge if it cannot operate in the next step.
        """

        power_demand = 0.0
        for rover in self.science_rovers:
            if rover.current_battery_kWh < rover.power_usage_kWh:
                power_demand += rover.battery_capacity_kWh - rover.current_battery_kWh

        return power_demand

    def step(self, available_power: float):
        """
        Execute one simulation step for the science sector.
        Distributes available power to rovers and collects generated science.
        """

        self.step_science_generated = 0.0
        total_power_used = 0.0
        remaining_power = available_power

        # Calculate power per rover (optional: distribute evenly)
        power_per_rover = remaining_power / len(self.science_rovers) if self.science_rovers else 0.0

        # Update each rover
        for i, rover in enumerate(self.science_rovers):
            # Probabilistic throttling: skip rover with probability = throttle_factor
            if random.random() < self.throttle_factor:
                # Rover is throttled - skip its step
                power_used = 0.0
                science_generated = 0.0
                rover.status = RoverStatus.THROTTLED
            else:
                # Rover operates normally - give it its share of power
                rover.status = RoverStatus.OPERATIONAL
                rover_power = min(power_per_rover, remaining_power)
                power_used, science_generated = rover.step(rover_power)
                remaining_power = max(0.0, remaining_power - power_used)

            total_power_used += power_used
            self.step_science_generated += science_generated

        # Update cumulative science
        self.total_science_cumulative += self.step_science_generated
        return total_power_used, self.step_science_generated

    def _create_metric_map(self) -> dict:
        """
        Create a map of all metric contributions from the science sector.
        This includes contributions from operational rovers and direct sector outputs.
        """

        metric_map = {}

        # 1. Calculate contributions based on operational agents from config
        if self.rover_configs:

            # Get the list of contributions from the first rover config (assumed to be the same for all)
            contributions_cfg = self.rover_configs[0].get("metric_contributions", [])
            # Count rovers that are currently operational (not throttled)
            operational_count = sum(1 for r in self.science_rovers if r.status == RoverStatus.OPERATIONAL)

            for contrib in contributions_cfg:
                metric_id = contrib.get("metric_id")
                value_per_agent = float(contrib.get("contribution_value", 0.0))
                contribution_type = contrib.get("contribution_type")

                if metric_id and contribution_type == "predefined":
                    # Calculate total contribution for this metric
                    total_contribution = operational_count * value_per_agent
                    metric_map[metric_id] = total_contribution

        return metric_map

    def get_metrics(self) -> dict:
        """
        Get current science sector metrics.
        """

        operational_rovers = sum(1 for r in self.science_rovers if r.status == RoverStatus.OPERATIONAL)

        return {
            "total_science_cumulative": self.total_science_cumulative,
            "science_generated": self.step_science_generated,
            "operational_rovers": operational_rovers,
            "total_rovers": self.rover_id_counter,
            "total_power_demand": self.get_power_demand(),
            "metric_contributions": self._create_metric_map(),
        }
