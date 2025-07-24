from mesa import Agent


class ScienceRover(Agent):
    def __init__(self, agent_config: dict):
        """
        Initializes a Science Rover agent using config dict from the world system builder.

        Args:
            agent_config (dict): Agent-specific configuration.
        """
        self.id = agent_config["id"]
        self.type = agent_config["type"]
        self.power_usage_kWh = agent_config["power_usage_kWh"]
        self.science_generation = agent_config["science_generation"]
        self.battery_capacity_kWh = agent_config["battery_capacity_kWh"]
        self.current_battery_kWh = agent_config.get("current_battery_kWh", self.battery_capacity_kWh)
        self.science_buffer = agent_config.get("science_buffer", 0.0)
        self.status = agent_config.get("status", "idle")
        self.location = agent_config.get("location", (0, 0))
        self.is_operational = False

    def is_fully_charged(self) -> bool:
        return self.current_battery_kWh >= self.battery_capacity_kWh

    def needs_charge(self) -> bool:
        return self.current_battery_kWh < self.battery_capacity_kWh

    def step(self, available_energy_kWh: float) -> tuple:
        """
        Run science generation or charge if needed.

        Returns:
            (float, float): Tuple (power_draw, science_generated)
        """
        power_draw = 0.0
        science_generated = 0.0

        if self.needs_charge():
            charge_needed = self.battery_capacity_kWh
            charge_this_step = min(charge_needed, available_energy_kWh)
            self.current_battery_kWh += charge_this_step
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
        return {
            "id": self.id,
            "battery_kWh": self.current_battery_kWh,
            "science_buffer": self.science_buffer,
            "status": self.status,
            "is_operational": self.is_operational,
            "type": "science_rover",
        }
