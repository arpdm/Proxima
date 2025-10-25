from mesa import Agent
from enum import Enum


class RoverStatus(Enum):
    """Enumeration of possible rover statuses."""

    IDLE = "idle"
    OPERATIONAL = "operational"
    CHARGING = "charging"
    LOW_BATTERY = "low_battery"
    THROTTLED = "throttled"


class ScienceRover(Agent):
    """
    A science rover that operates on battery power, generates science, and recharges
    from the grid when its battery is too low to operate.
    """

    def __init__(self, unique_id, model, agent_config: dict):
        """
        Initializes a Science Rover agent.

        Args:
            unique_id: A unique identifier for the agent.
            model: The model instance the agent belongs to.
            agent_config (dict): Agent-specific configuration.
        """
        super().__init__(model)

        config = agent_config.get("config", agent_config)
        self.config = config

        # Characteristics
        self.power_usage_kWh = float(config.get("power_usage_kWh", 0.2))
        self.science_generation = float(config.get("science_generation", 0.5))
        self.battery_capacity_kWh = float(config.get("battery_capacity_kWh", 20))

        # State variables
        self.current_battery_kWh = float(config.get("current_battery_kWh", self.battery_capacity_kWh))
        self.science_buffer = float(config.get("science_buffer", 0.0))
        self.status = RoverStatus(config.get("status", RoverStatus.IDLE.value))
        self.location = config.get("location", (0, 0))

    def step(self, available_energy_kWh: float) -> tuple:
        """
        Defines the rover's behavior for a single simulation step.
        The rover prioritizes operating. If it cannot, it attempts to charge.

        Returns:
            A tuple of (power_draw_from_grid, science_generated).
        """
        power_draw_from_grid = 0.0
        science_generated = 0.0

        # --- Prioritize operating ---
        if self.current_battery_kWh >= self.power_usage_kWh:
            # If we have enough power, operate
            self.current_battery_kWh -= self.power_usage_kWh
            self.science_buffer += self.science_generation
            science_generated = self.science_generation
            self.status = RoverStatus.OPERATIONAL
        else:
            # If we can't operate, try to charge ---
            self.status = RoverStatus.CHARGING
            charge_needed = self.battery_capacity_kWh - self.current_battery_kWh
            charge_this_step = min(charge_needed, available_energy_kWh)

            self.current_battery_kWh += charge_this_step
            power_draw_from_grid = charge_this_step

            # If still not enough power to operate after charging, status is low battery
            if self.current_battery_kWh < self.power_usage_kWh:
                self.status = RoverStatus.LOW_BATTERY

        return power_draw_from_grid, science_generated

    def report(self) -> dict:
        """
        Returns a dictionary of current state for logging or visualization.
        """
        battery_percentage = (
            (self.current_battery_kWh / self.battery_capacity_kWh) * 100 if self.battery_capacity_kWh > 0 else 0
        )

        return {
            "battery_kWh": round(self.current_battery_kWh, 2),
            "battery_percentage": round(battery_percentage, 1),
            "battery_capacity_kWh": self.battery_capacity_kWh,
            "science_buffer": round(self.science_buffer, 2),
            "status": self.status.value,  # Return string value for compatibility
            "is_operational": self.status == RoverStatus.OPERATIONAL,
            "type": "science_rover",
        }
