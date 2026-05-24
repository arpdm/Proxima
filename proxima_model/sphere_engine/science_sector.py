"""
science_sector.py

Manages all science-related activities in the Proxima simulation.
Handles science rovers, research operations, and power management.
"""

from dataclasses import dataclass
from typing import Dict, List, Any

from proxima_model.components.science_rover import ScienceRover, RoverStatus
from proxima_model.world_system.world_system_defs import EventType

import random
import logging
import math


@dataclass
class ScienceSectorConfig:
    """Scalar configuration for the science sector."""

    sector_name: str = "science"

    throttle_factor: float = 0.0  # 0.0 = no throttling, 1.0 = always throttled

    # Growth policy parameters (see science_policies.md)
    growth_duration_sp: int = 1  # Steps over which growth rate is measured
    lead_time_L: int = 1  # Expected lead time for rover deployment (months)
    planning_horizon_H: int = 60  # Receding-horizon planning window (steps)
    safety_margin_beta: float = 0.1  # Safety margin fraction (10%)

    # Growth States
    current_growth_rate: float = 0.0  # Growth rate r in S(t) = S_0 * 2^(r*t)
    S_0 = 0.0  # Science production rate at the start of the growth duration window
    rovers_in_pipeline = 0
    expected_loasses = 0
    total_science_cumulative: float = 0.0
    operational_rovers: int = 0
    total_rovers: int = 0
    p_eff: float = 0  # Effective Productivity

    # Pipeline constraints
    max_pipeline_capacity: int = 10  # Maximum rovers that can be in pipeline at once

    # Rover performance factors
    availability_factor_a: float = 1.0  # Reliability factor (1.0 = perfect reliability)
    utilization_factor_u: float = 1.0  # Utilization factor (power/crew/comms limitations)


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
        self.event_bus = event_bus

        # Load scalar sector config via field overlay (matches construction sector pattern)
        config_kwargs = {}
        for field_name in ScienceSectorConfig.__dataclass_fields__.keys():
            if field_name in config:
                config_kwargs[field_name] = config[field_name]
        self._config = ScienceSectorConfig(**config_kwargs)
        self.science_rovers = []

        # Growth rate tracking - runtime state, not config
        self.science_history = []  # Store (step, science_rate) tuples
        self.nominal_productivity_p = 0.0  # Calculated in _initialize_rovers from rover config

        # Event Subscribtions
        self.event_bus.subscribe(EventType.MODULE_COMPLETED.value, self.handle_module_completed)
        self._initialize_rovers(config)

        # If latest_state.science is provided (from world_system.latest_state), hydrate metrics/state.
        latest_state_science = config.get("latest_state") if isinstance(config, dict) else None
        if latest_state_science:
            self._apply_latest_state(latest_state_science)

    def _initialize_rovers(self, config: dict):
        """Initialize all science rovers from config."""

        self.rover_configs = config.get("science_rovers", [])
        self.nominal_productivity_p = (
            self.rover_configs[0].get("config", {}).get("science_generation", 0.5) if self.rover_configs else 0.5
        )

        for rover_config in self.rover_configs:
            quantity = rover_config.get("quantity", 1)
            for _ in range(quantity):
                self._create_rover(rover_config)

    def _create_rover(self, rover_config: dict, *, increment_total: bool = True):
        """Create a single science rover."""

        unique_id = f"science_rover_{self._config.total_rovers}"
        rover = ScienceRover(unique_id, self.model, rover_config)
        self.science_rovers.append(rover)
        if increment_total:
            self._config.total_rovers += 1
        logger_science.info(f"Created {unique_id}")
        return rover

    def _apply_latest_state(self, science_state: dict) -> None:
        """Restore science sector counters and metrics from a latest_state snapshot."""

        # Core counters
        self._config.total_science_cumulative = float(science_state.get("total_science_cumulative", 0.0))
        saved_total_rovers = int(science_state.get("total_rovers", self._config.total_rovers))
        self._config.total_rovers = saved_total_rovers
        self._config.operational_rovers = int(science_state.get("operational_rovers", 0))
        self._config.rovers_in_pipeline = int(science_state.get("rovers_in_pipeline", 0))

        # Growth / productivity
        self._config.current_growth_rate = float(science_state.get("science_growth_rate", 0.0))
        self._config.S_0 = float(science_state.get("S_0", self._config.S_0))
        self._config.p_eff = float(science_state.get("p_eff", 0.0))

        # Last step science output (for continuity)
        self.step_science_generated = float(science_state.get("science_generated", 0.0))

        # If total_rovers in state exceeds spawned agents, top up creations to match count
        missing = saved_total_rovers - len(self.science_rovers)
        if missing > 0 and self.rover_configs:
            base_cfg = self.rover_configs[0]
            for _ in range(missing):
                self._create_rover(base_cfg, increment_total=False)

        # Ensure counter matches saved value
        self._config.total_rovers = saved_total_rovers

    def handle_module_completed(self, requesting_sphere: str, module_id: str, **kwargs):
        """Handle newly constructed modules."""

        # Only process if it's for us and it's a science rover
        if requesting_sphere != self._config.sector_name:
            return

        if module_id != "comp_science_rover":
            return

        # Get base config from our existing rovers
        if not self.rover_configs:
            logger_science.error("Cannot add rover: no config available")
            return

        base_config = self.rover_configs[0]
        new_rover = self._create_rover(base_config)

        # Decrement pipeline count
        if self._config.rovers_in_pipeline > 0:
            self._config.rovers_in_pipeline -= 1
            logger_science.info(
                f"✅ Added new science rover: {new_rover.unique_id} "
                f"(total: {len(self.science_rovers)}, pipeline: {self._config.rovers_in_pipeline})"
            )
        else:
            logger_science.info(
                f"✅ Added new science rover: {new_rover.unique_id} "
                f"(total: {len(self.science_rovers)}) - not from pipeline order"
            )

    def set_throttle_factor(self, throttle_value: float):
        """Set throttle factor for probabilistic rover operation (0.0 to 1.0)."""

        self._config.throttle_factor = max(0.0, min(1.0, throttle_value))  # Clamp to 0-1

    def get_power_demand(self) -> float:
        """
        Calculate total power demand from all rovers that need to charge.
        A rover needs to charge if it cannot operate in the next step.
        """

        power_demand = 0.0
        for rover in self.science_rovers:
            if rover.current_battery_kWh < rover.power_usage_kWh_per_step:
                power_demand += rover.battery_capacity_kWh - rover.current_battery_kWh

        return power_demand

    def control_science_growth_rate(self, growth_rate: float, growth_duration: int):
        """
        Set the science sector growth policy parameters.

        Args:
            growth_rate: Target growth rate (1/doubling_steps)
            growth_duration: Duration over which to measure growth
        """
        self._config.growth_duration_sp = growth_duration  # Steps
        self.growth_rate_sp = growth_rate
        self._apply_growth_algorithm(self.model.steps)

        logger_science.info(
            f"Science Sector Policy Applied - "
            f"Target: growth rate {self.growth_rate_sp:.2f}, "
            f"Growth duration: {growth_duration} steps"
        )

    def _calculate_growth_rate(self):
        """
        Calculate the current growth rate over the configured duration.
        Updates both current_growth_rate and S_0.

        The growth follows: S(t) = S_0 * 2^(r*t)
        Where:
            r = growth_rate
            S_0 = science production at the start of the growth duration window
        """

        if len(self.science_history) < 2:
            # Not enough data yet
            self._config.current_growth_rate = 0.0
            self._config.S_0 = self.step_science_generated if hasattr(self, "step_science_generated") else 0.0
            return

        # Get measurements from growth rate duration setpoint
        window_start = int(max(0, len(self.science_history) - self._config.growth_duration_sp))
        start_month, S_0_new = self.science_history[window_start]
        current_month, S_current = self.science_history[-1]

        # Update S_0 to the science rate at the start of the window
        self._config.S_0 = S_0_new

        # Avoid division by zero or negative rates
        if self._config.S_0 <= 0 or S_current <= 0:
            self._config.current_growth_rate = 0.0
            return

        # Calculate actual time elapsed
        t_elapsed = current_month - start_month
        if t_elapsed <= 0:
            self._config.current_growth_rate = 0.0
            return

        # From S(t) = S_0 * 2^(r*t), solve for r:
        # r = log2(S_current / S_0) / t_elapsed
        growth_ratio = S_current / self._config.S_0
        if growth_ratio <= 0:
            self._config.current_growth_rate = 0.0
            return

        self._config.current_growth_rate = math.log2(growth_ratio) / t_elapsed

    def _apply_growth_algorithm(self, t: int):
        """
        Apply the receding-horizon growth algorithm to order rovers.

        Algorithm from science_policies.md:
        1. Calculate effective productivity: p_eff = p * a * u
        2. Compute future target: S_target(t+H) = S_0 * growth_rate^((t+H)/doubling_months)
        3. Determine required rovers: R_req = ceil(S_target / p_eff)
        4. Forecast expected rovers: R_fore = R_active - Losses + pipeline
        5. Order rovers: q(t) = max(0, ceil((1+β)*R_req) - R_fore)
        6. Apply pipeline capacity constraint

        Args:
            t: Current time (month)
        """

        # Step 1: Calculate effective productivity p_eff = p * a * u
        operational_count = sum(1 for r in self.science_rovers if r.status == RoverStatus.OPERATIONAL)
        if len(self.science_rovers) > 0:
            self._config.availability_factor_a = operational_count / len(self.science_rovers)
        else:
            self._config.availability_factor_a = 1.0

        self._config.utilization_factor_u = 1.0 - self._config.throttle_factor
        p_eff = self.nominal_productivity_p * self._config.availability_factor_a * self._config.utilization_factor_u

        # Step 2: Calculate target science rate at horizon S_target(t+H)
        if self._config.S_0 <= 0:
            # Use current rate if S_0 not established yet
            self._config.S_0 = getattr(self, "step_science_generated", 0.0)

        S_target = self._config.S_0 * (
            self.growth_rate_sp ** ((t + self._config.planning_horizon_H) / self._config.growth_duration_sp)
        )

        # Step 3: Calculate required rovers R_req = ceil(S_target / p_eff)
        if p_eff > 0:
            R_req = math.ceil(S_target / p_eff)
        else:
            R_req = 0

        # Step 4: Forecast available rovers R_fore = Total Rovers - Losses + pipeline
        R_fore = self._config.total_rovers - self._config.expected_loasses + self._config.rovers_in_pipeline
        R_fore = max(0, R_fore)

        # Step 5: Calculate order quantity q(t) = max(0, ceil((1+β)*R_req) - R_fore)
        q = max(0, math.ceil((1 + self._config.safety_margin_beta) * R_req) - R_fore)

        # Step 6: Apply pipeline capacity constraint
        available_pipeline_capacity = self._config.max_pipeline_capacity - self._config.rovers_in_pipeline
        q_capped = min(q, available_pipeline_capacity)

        if q_capped < q:
            logger_science.warning(
                f"Pipeline capacity constraint: requested {q} rovers, "
                f"but only {q_capped} can be ordered "
                f"(pipeline: {self._config.rovers_in_pipeline}/{self._config.max_pipeline_capacity})"
            )

        logger_science.info(
            f"Growth Algorithm (t={t}): "
            f"S_0={self._config.S_0:.2f}, "
            f"S_target={S_target:.2f}, "
            f"p_eff={p_eff:.3f}, "
            f"R_req={R_req}, "
            f"R_total={self._config.total_rovers}, "
            f"pipeline={self._config.rovers_in_pipeline}/{self._config.max_pipeline_capacity}, "
            f"R_fore={R_fore}, "
            f"order_requested={q}, "
            f"order_actual={q_capped}"
        )

        # Step 7: Place order if needed
        if q_capped > 0:
            self._config.rovers_in_pipeline += q_capped

            logger_science.info(
                f"📦 Ordering {q_capped} rovers "
                f"(expected delivery: ~month {t + self._config.lead_time_L}, "
                f"total in pipeline: {self._config.rovers_in_pipeline}/{self._config.max_pipeline_capacity})"
            )

            # Send event to logistics/manufacturing sector
            # Send separate request for each rover to ensure accurate pipeline tracking
            for _ in range(q_capped):
                self.event_bus.publish(
                    EventType.CONSTRUCTION_REQUEST.value,
                    requesting_sphere=self._config.sector_name,
                    module_id="comp_science_rover",
                    shell_quantity=1,
                )

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
            if random.random() < self._config.throttle_factor:
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
        self._config.total_science_cumulative += self.step_science_generated

        # Track science production rate history
        self.science_history.append((self.model.steps, self.step_science_generated))

        # Keep only the 2x the measurement window to avoid unbounded growth
        max_history_length = int(self._config.growth_duration_sp * 2)
        if len(self.science_history) > max_history_length:
            self.science_history = self.science_history[-max_history_length:]

        # Calculate current growth rate (updates both current_growth_rate and S_0)
        self._calculate_growth_rate()
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
                    # Note: Decay is already scaled by time_scale, contributions use base rates
                    total_contribution = operational_count * value_per_agent
                    metric_map[metric_id] = total_contribution

        return metric_map

    def get_metrics(self) -> dict:
        """
        Get current science sector metrics.
        """

        self._config.operational_rovers = sum(1 for r in self.science_rovers if r.status == RoverStatus.OPERATIONAL)

        return {
            "total_science_cumulative": self._config.total_science_cumulative,
            "science_generated": self.step_science_generated,
            "operational_rovers": self._config.operational_rovers,
            "total_rovers": self._config.total_rovers,
            "total_power_demand": self.get_power_demand(),
            "metric_contributions": self._create_metric_map(),
            "science_growth_rate": self._config.current_growth_rate,
            "S_0": self._config.S_0,
            "rovers_in_pipeline": self._config.rovers_in_pipeline,
            "p_eff": self.nominal_productivity_p
            * self._config.availability_factor_a
            * self._config.utilization_factor_u,
        }
