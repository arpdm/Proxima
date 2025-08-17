from mesa import Agent


class FuelGenerator(Agent):
    """
    FuelGenerator agent for simulating lunar fuel production.

    Attributes:
        config (dict): Configuration dictionary for the agent.
        efficiency (float): Conversion efficiency of the generator (default 0.5).
        thermal_GWh_per_kg (float): Thermal energy available per kg of he3 (default 163.9 GWh/kg).
        kwh_per_kg_prop (float): kWh required to generate one kg of propellant (default 22.8).
        he3_kg_per_hour (float): Amount of He3 processed per hour (default 5 kg).
        is_operational (bool): Operational status of the generator.
    """

    def __init__(self, agent_config: dict):
        """
        Initialize a FuelGenerator agent.

        Args:
            agent_config (dict): Agent-specific configuration. Should contain keys:
        """
        config = agent_config.get("config", agent_config)
        self.config = config
        self.efficiency = config.get("efficiency", 0.5)
        self.thermal_GWh_per_kg = config.get("thermal_GWh_per_kg", 163.9)
        self.kwh_per_kg_prop = agent_config.get("kwh_per_kg_prop", 22.8)
        self.he3_kg_per_hour = agent_config.get("he3_kg_per_hour", 5)
        self.is_operational = False

    def step(self, available_he3_kg: float) -> tuple:
        """
        Simulate one time step of fuel generation.

        Args:
            available_he3_kg (float): Amount of He3 available for processing.

        Returns:
            tuple: (he3_kg_consumed, prop_generated_kg)
                - he3_kg_consumed (float): He3 consumed to generate prop
                - prop_generated_kg (float): Amount of propellant generated.
        """
        prop_generated_kg = 0.0

        if available_he3_kg >= self.he3_kg_per_hour:
            kwh_available = self.thermal_GWh_per_kg * 1e6 * self.efficiency  # Convert GWh to kWh
            prop_generated_kg = (kwh_available * self.he3_kg_per_hour) / self.kwh_per_kg_prop
            return available_he3_kg, prop_generated_kg
        else:
            self.is_operational = False

        return 0.0, prop_generated_kg  # No power drawn from grid when not operating

    def report(self) -> dict:
        """
        Return a dictionary of the current state for logging or visualization.

        Returns:
            dict: Status snapshot with operational status
        """

        return {
            "is_operational": self.is_operational,
            "type": "fuel_gen",
        }
