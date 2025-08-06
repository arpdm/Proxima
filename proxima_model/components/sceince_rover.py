from mesa import Agent


class ScienceRover(Agent):
    def __init__(self, agent_config: dict):
        """
        Initializes a Science Rover agent using config dict from the world system builder.

        Args:
            agent_config (dict): Agent-specific configuration.
        """
        config = agent_config.get("config", agent_config)

        # No ID field needed - be consistent with PowerGenerator/PowerStorage
        self.config = config
        self.power_usage_kWh = config.get("power_usage_kWh", 0.2)
        self.science_generation = config.get("science_generation", 0.5)
        self.battery_capacity_kWh = config.get("battery_capacity_kWh", 20)
        self.current_battery_kWh = agent_config.get("current_battery_kWh", self.battery_capacity_kWh)
        self.science_buffer = agent_config.get("science_buffer", 0.0)
        self.status = agent_config.get("status", "idle")
        self.location = agent_config.get("location", (0, 0))
        self.is_operational = False

    def is_fully_charged(self) -> bool:
        return self.current_battery_kWh >= self.battery_capacity_kWh

    def needs_charge(self) -> bool:
        return self.current_battery_kWh < self.power_usage_kWh

    def step(self, available_energy_kWh: float) -> tuple:
        """
        Run science generation or charge if needed.

        Returns:
            (float, float): Tuple (power_draw, science_generated)
        """
        power_draw = 0.0
        science_generated = 0.0

        if self.needs_charge():
            # Fix: Calculate actual charge needed (remaining capacity)
            charge_needed = self.battery_capacity_kWh - self.current_battery_kWh
            charge_this_step = min(charge_needed, available_energy_kWh)
            self.current_battery_kWh += charge_this_step

            # Ensure we don't exceed capacity (safety check)
            self.current_battery_kWh = min(self.current_battery_kWh, self.battery_capacity_kWh)

            power_draw = charge_this_step
            self.status = "charging"
            self.is_operational = False
            return power_draw, 0.0

        if self.current_battery_kWh >= self.power_usage_kWh:
            self.current_battery_kWh -= self.power_usage_kWh
            self.science_buffer += self.science_generation
            science_generated = self.science_generation
            self.status = "operational"
            self.is_operational = True
        else:
            self.status = "low_battery"
            self.is_operational = False

        return 0.0, science_generated  # No power drawn from grid when operating

    def report(self) -> dict:
        """
        Returns a dictionary of current state for logging or visualization.

        Returns:
            dict: Status snapshot.
        """
        battery_percentage = (
            (self.current_battery_kWh / self.battery_capacity_kWh) * 100 if self.battery_capacity_kWh > 0 else 0
        )

        return {
            "battery_kWh": round(self.current_battery_kWh, 2),
            "battery_percentage": round(battery_percentage, 1),
            "battery_capacity_kWh": self.battery_capacity_kWh,
            "science_buffer": round(self.science_buffer, 2),
            "status": self.status,
            "is_operational": self.is_operational,
            "type": "science_rover",
        }
