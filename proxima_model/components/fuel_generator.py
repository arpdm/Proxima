from mesa import Agent


class FuelGenerator(Agent):
    """Converts He-3 into rocket propellant, gated by allocated grid power."""

    def __init__(self, model, agent_config: dict):
        super().__init__(model)

        config = agent_config.get("config", agent_config) or {}
        self.config = config
        self.efficiency = float(config.get("efficiency", 0.025))
        self.thermal_GWh_per_kg = float(config.get("thermal_GWh_per_kg", 163.489))
        self.kwh_per_kg_prop = float(config.get("kwh_per_kg_prop", 50.0))
        self.he3_kg_per_step = float(config.get("he3_kg_per_hour", 5)) * model.time_scale
        self.power_demand_kWh_per_step = float(config.get("power_demand_kWh_per_step", 65.0))

        self.is_operational = False
        self.is_throttled = False
        self.prop_generated_kg = 0.0
        self.power_consumed_step = 0.0

    def _he3_process_capacity(self, available_he3_kg: float) -> float:
        """He-3 this generator can process this step, capped by available supply."""
        return min(max(0.0, available_he3_kg), self.he3_kg_per_step)

    def _propellant_from_he3(self, he3_processed_kg: float) -> float:
        """Propellant (kg) produced from processed He-3, per the documented equation."""
        if self.kwh_per_kg_prop <= 0:
            raise ValueError("kwh_per_kg_prop must be > 0")

        kwh_per_kg_he3 = self.thermal_GWh_per_kg * 1e6
        kwh_available = he3_processed_kg * kwh_per_kg_he3 * self.efficiency
        return float(kwh_available / self.kwh_per_kg_prop)

    def get_power_demand(self, available_he3_kg: float = None) -> float:
        """Grid energy needed this step, scaled by how much He-3 can actually be processed."""
        if self.he3_kg_per_step <= 0:
            return 0.0

        he3_available = self.he3_kg_per_step if available_he3_kg is None else available_he3_kg
        processing_fraction = self._he3_process_capacity(he3_available) / self.he3_kg_per_step
        return float(self.power_demand_kWh_per_step * processing_fraction)

    def step(self, available_he3_kg: float, allocated_power: float = None) -> tuple:
        """Process available He-3 into propellant, throttled by allocated_power if given.

        Returns:
            (he3_consumed_kg, prop_generated_kg)
        """
        self.prop_generated_kg = 0.0
        self.power_consumed_step = 0.0
        self.is_throttled = False

        he3_capacity = self._he3_process_capacity(available_he3_kg)
        power_demand = self.get_power_demand(available_he3_kg)
        if he3_capacity <= 0 or power_demand <= 0:
            self.is_operational = False
            return 0.0, 0.0

        usable_power = power_demand if allocated_power is None else max(0.0, min(allocated_power, power_demand))
        if usable_power <= 0:
            self.is_operational = False
            self.is_throttled = True
            return 0.0, 0.0

        power_fraction = usable_power / power_demand
        he3_consumed = he3_capacity * power_fraction
        self.prop_generated_kg = self._propellant_from_he3(he3_consumed)
        self.power_consumed_step = usable_power
        self.is_operational = True
        self.is_throttled = power_fraction < 1.0

        return float(he3_consumed), float(self.prop_generated_kg)

    def report(self) -> dict:
        """Current state snapshot for logging or visualization."""
        return {
            "is_operational": self.is_operational,
            "is_throttled": self.is_throttled,
            "type": "fuel_gen",
            "generated_prop_kg": self.prop_generated_kg,
            "power_consumed": self.power_consumed_step,
            "power_demand": self.get_power_demand(),
        }
