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
        self.efficiency = config.get("efficiency", 0.025)
        self.thermal_GWh_per_kg = config.get("thermal_GWh_per_kg", 163.489)
        self.kwh_per_kg_prop = agent_config.get("kwh_per_kg_prop", 50.0)
        self.he3_kg_per_hour = agent_config.get("he3_kg_per_hour", 5)
        self.is_operational = False

    def step(self, available_he3_kg: float) -> tuple:
        """
        Process up to self.he3_kg_per_hour of He-3 and produce propellant.

        Args:
            available_he3_kg (float): He-3 available to consume this hour.

        Returns:
            (he3_consumed_kg: float, prop_generated_kg: float)
        """
        if available_he3_kg <= 0:
            self.is_operational = False
            return 0.0, 0.0

        # Determine how much He-3 can actually be processed this timestep
        he3_to_process = min(self.he3_kg_per_hour, available_he3_kg)
        self.is_operational = he3_to_process > 0.0

        # Convert thermal_GWh_per_kg -> kWh/kg (1 GWh = 1e6 kWh)
        kwh_per_kg_he3 = self.thermal_GWh_per_kg * 1e6

        # kWh actually available after efficiency losses for the processed He-3
        kwh_available = kwh_per_kg_he3 * he3_to_process * self.efficiency

        # Propellant produced (kg) = available kWh / kWh per kg propellant
        # Guard against division by zero
        if self.kwh_per_kg_prop <= 0:
            raise ValueError("kwh_per_kg_prop must be > 0")

        self.prop_generated_kg = kwh_available / self.kwh_per_kg_prop

        # Return amount consumed and prop produced
        return float(he3_to_process), float(self.prop_generated_kg)

    def report(self) -> dict:
        """
        Return a dictionary of the current state for logging or visualization.

        Returns:
            dict: Status snapshot with operational status
        """

        return {
            "is_operational": self.is_operational,
            "type": "fuel_gen",
            "generated_prop_kg" : self.prop_generated_kg
        }