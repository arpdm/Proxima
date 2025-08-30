"""
fusion_agents_time_aware.py

Time-aware He-3 agents (deuterium ignored):
- FuelGenerator: He-3 → electricity → propellant
- He3FusionReactor: He-3 → electricity

Both scale cleanly with the simulation time step. If you pass `dt_hours` to
`step(...)` we use it; otherwise we auto-discover a default from:
    getattr(self.model, "delta_t", 1.0)    # hours per step

So if one step = 1 hour, results are per-hour; if one step = 1 month, set
`model.delta_t = 720` (or your month-hours), and results become per-month.

Units used throughout:
- thermal_GWh_per_kg   (GWh / kg He-3)
- efficiency           (0..1), electric = thermal × efficiency
- electric_MWh_per_kg  (MWh / kg He-3) = thermal_GWh_per_kg × 1000 × efficiency
- he3_kg_per_hour      (kg/h) cap; actual burn this step = cap × dt_hours (capped by availability)
"""
from __future__ import annotations
from typing import Dict, Tuple, Optional

from mesa import Agent

KWH_PER_GWH = 1_000_000.0
MWH_PER_GWH = 1_000.0


def _dt(self, dt_hours: Optional[float]) -> float:
    if dt_hours is not None:
        return float(dt_hours)
    # Fallback to model.delta_t if present, else 1 hour
    return float(getattr(self.model, "delta_t", 1.0))


class FuelGenerator(Agent):
    """He-3 → Electricity → Propellant (time-aware, no deuterium).

    Config keys (defaults):
      efficiency: 0.50
      thermal_GWh_per_kg: 166.4   # 19 MW·yr ≈ 166.4 GWh (you may set 163.9 if preferred)
      kwh_per_kg_prop: 22.8
      he3_kg_per_hour: 0.00012    # ≈ 10 MW cap with defaults
    """
    def __init__(self, unique_id, model, agent_config: dict):
        super().__init__(unique_id, model)
        cfg = agent_config.get("config", agent_config) or {}
        self.efficiency: float = float(cfg.get("efficiency", 0.50))
        self.thermal_GWh_per_kg: float = float(cfg.get("thermal_GWh_per_kg", 166.4))
        self.kwh_per_kg_prop: float = float(cfg.get("kwh_per_kg_prop", 22.8))
        self.he3_kg_per_hour: float = float(cfg.get("he3_kg_per_hour", 0.00012))
        # State
        self.is_operational: bool = False
        self.last_he3_consumed: float = 0.0
        self.last_propellant_kg: float = 0.0
        self.last_energy_MWh: float = 0.0
        self.last_avg_power_MW: float = 0.0

    # Derived energy constants
    @property
    def electric_MWh_per_kg(self) -> float:
        return self.thermal_GWh_per_kg * MWH_PER_GWH * self.efficiency

    @property
    def electric_kWh_per_kg(self) -> float:
        return self.thermal_GWh_per_kg * KWH_PER_GWH * self.efficiency

    def step(self, available_he3_kg: float, dt_hours: Optional[float] = None) -> Tuple[float, float]:
        dt = _dt(self, dt_hours)
        if dt <= 0:
            self.is_operational = False
            self.last_he3_consumed = 0.0
            self.last_propellant_kg = 0.0
            self.last_energy_MWh = 0.0
            self.last_avg_power_MW = 0.0
            return 0.0, 0.0

        # Burn rate limited by cap and availability
        he3_cap_this_step = self.he3_kg_per_hour * dt
        he3_consumed = max(0.0, min(available_he3_kg, he3_cap_this_step))
        if he3_consumed <= 0.0:
            self.is_operational = False
            self.last_he3_consumed = 0.0
            self.last_propellant_kg = 0.0
            self.last_energy_MWh = 0.0
            self.last_avg_power_MW = 0.0
            return 0.0, 0.0

        # Electric energy this step (MWh) and average power (MW)
        E_step_MWh = he3_consumed * self.electric_MWh_per_kg
        P_avg_MW = E_step_MWh / dt

        # Convert electricity to propellant mass
        prop_kg = (E_step_MWh * 1000.0) / self.kwh_per_kg_prop

        self.is_operational = True
        self.last_he3_consumed = he3_consumed
        self.last_propellant_kg = prop_kg
        self.last_energy_MWh = E_step_MWh
        self.last_avg_power_MW = P_avg_MW
        return he3_consumed, prop_kg

    def report(self) -> Dict[str, float]:
        return {
            "type": "fuel_generator",
            "is_operational": self.is_operational,
            "electric_MWh_per_kg": self.electric_MWh_per_kg,
            "he3_cap_kg_per_hour": self.he3_kg_per_hour,
            "last_he3_consumed_kg": self.last_he3_consumed,
            "last_energy_MWh": self.last_energy_MWh,
            "last_avg_power_MW": self.last_avg_power_MW,
            "last_propellant_kg": self.last_propellant_kg,
        }


class He3FusionReactor(Agent):
    """He-3 → Electricity (time-aware, no deuterium).

    Config keys (defaults):
      efficiency: 0.50
      thermal_GWh_per_kg: 166.4
      he3_kg_per_hour: 0.00012
    """
    def __init__(self, unique_id, model, agent_config: dict):
        super().__init__(unique_id, model)
        cfg = agent_config.get("config", agent_config) or {}
        self.efficiency: float = float(cfg.get("efficiency", 0.50))
        self.thermal_GWh_per_kg: float = float(cfg.get("thermal_GWh_per_kg", 166.4))
        self.he3_kg_per_hour: float = float(cfg.get("he3_kg_per_hour", 0.00012))
        # State
        self.is_online: bool = False
        self.last_he3_consumed: float = 0.0
        self.last_energy_MWh: float = 0.0
        self.last_avg_power_MW: float = 0.0

    @property
    def electric_MWh_per_kg(self) -> float:
        return self.thermal_GWh_per_kg * MWH_PER_GWH * self.efficiency

    def step(
        self,
        available_he3_kg: float,
        requested_power_MW: Optional[float] = None,
        dt_hours: Optional[float] = None,
    ) -> Tuple[float, float]:
        """Run one time step.
        Returns (he3_consumed_kg, electricity_MWh_this_step)
        """
        dt = _dt(self, dt_hours)
        if dt <= 0:
            self.is_online = False
            self.last_he3_consumed = 0.0
            self.last_energy_MWh = 0.0
            self.last_avg_power_MW = 0.0
            return 0.0, 0.0

        # Determine desired burn from requested power (if any)
        if requested_power_MW is not None and requested_power_MW > 0.0:
            he3_rate_needed = requested_power_MW / self.electric_MWh_per_kg  # kg/h
        else:
            he3_rate_needed = self.he3_kg_per_hour

        he3_cap_this_step = self.he3_kg_per_hour * dt
        he3_needed_this_step = he3_rate_needed * dt
        he3_consumed = max(0.0, min(available_he3_kg, he3_cap_this_step, he3_needed_this_step))
        if he3_consumed <= 0.0:
            self.is_online = False
            self.last_he3_consumed = 0.0
            self.last_energy_MWh = 0.0
            self.last_avg_power_MW = 0.0
            return 0.0, 0.0

        E_step_MWh = he3_consumed * self.electric_MWh_per_kg
        P_avg_MW = E_step_MWh / dt

        self.is_online = True
        self.last_he3_consumed = he3_consumed
        self.last_energy_MWh = E_step_MWh
        self.last_avg_power_MW = P_avg_MW
        return he3_consumed, E_step_MWh

    def report(self) -> Dict[str, float]:
        return {
            "type": "he3_fusion_reactor",
            "is_online": self.is_online,
            "electric_MWh_per_kg": self.electric_MWh_per_kg,
            "he3_cap_kg_per_hour": self.he3_kg_per_hour,
            "last_he3_consumed_kg": self.last_he3_consumed,
            "last_energy_MWh": self.last_energy_MWh,
            "last_avg_power_MW": self.last_avg_power_MW,
        }



        # {
        #   "template_id": "comp_power_gen_nuclear",
        #   "subtype": "nuclear_fission",
        #   "config": {
        #     "power_capacity_kwh": 40,
        #     "efficiency": 0.8,
        #     "availability": 0.95
        #   },
        #   "quantity": 20
        # },
        # {
        #   "template_id": "comp_fuel_gen_rocket",
        #   "subtype": "liquid_rocket_fuel",
        #   "quantity": 3
        # }