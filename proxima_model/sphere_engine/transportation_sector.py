"""
Transportation Sector Manager

Manages rocket fleet, fuel generation, and transport requests between Earth and Moon.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Optional, Any
from proxima_model.components.rocket import Rocket, MissionPhase
from proxima_model.components.fuel_generator import FuelGenerator
from proxima_model.world_system.world_system_defs import EventType, SectorType

import logging

logger = logging.getLogger(__name__)

PLANET_DISTANCE_KM: Dict[tuple[str, str], float] = {
    ("earth", "moon"): 384400.0,
    ("moon", "earth"): 384400.0,
}


def get_planet_distance_km(origin: str, destination: str) -> float:
    """Return the configured average distance between two celestial bodies."""
    try:
        return PLANET_DISTANCE_KM[(origin.lower(), destination.lower())]
    except KeyError as exc:
        raise ValueError(f"No distance configured between {origin} and {destination}") from exc


class TransportRequestStatus(Enum):
    """Status of transport requests."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class TransportRequest:
    """Represents a transport request."""

    requesting_sector: str
    payload: Dict[str, float]
    origin: str
    destination: str
    status: str = "queued"

    def __post_init__(self):
        """Validate request after initialization."""
        if not self.payload:
            raise ValueError("Payload cannot be empty")
        if self.origin == self.destination:
            raise ValueError("Origin and destination cannot be the same")


@dataclass
class TransportationConfig:
    """Configuration for transportation sector."""

    sector_name: str = SectorType.TRANSPORTATION.value
    earth_moon_distance_km: Optional[float] = None
    loading_time_steps: int = 24
    he3_request_threshold_kg: float = 1.0
    minimum_fuel_k_sp: int = 5000

    def __post_init__(self):
        """Validate configuration."""
        if self.earth_moon_distance_km is not None and self.earth_moon_distance_km <= 0:
            raise ValueError("Distance must be positive")
        if self.loading_time_steps < 0:
            raise ValueError("Loading time must be non-negative")


@dataclass
class ResourceStocks:
    """Internal resource stocks for transportation sector."""

    rocket_fuel_kg: float = 0.0
    he3_kg: float = 0.0

    def __post_init__(self):
        """Validate stocks."""
        if self.rocket_fuel_kg < 0 or self.he3_kg < 0:
            raise ValueError("Stock values cannot be negative")


class TransportationSector:
    """Manages rocket fleet, fuel generation, and transport logistics."""

    def __init__(self, model, config: Dict[str, Any], event_bus):
        self.model = model
        self.event_bus = event_bus
        self._fuel_request_pending = False

        # Load configuration dynamically from config dict
        config_kwargs = {}
        for field_name in TransportationConfig.__dataclass_fields__.keys():
            if field_name in config:
                config_kwargs[field_name] = config[field_name]

        self._config = TransportationConfig(**config_kwargs)

        # Initialize stocks
        self._stocks = ResourceStocks()

        # Transport queue
        self.transport_queue: List[TransportRequest] = []

        # Initialize rocket fleet from config
        self.rockets: List[Rocket] = []
        self.rocket_configs = config.get("rockets", [])
        for rocket_config in self.rocket_configs:
            rocket_quantity = rocket_config.get("quantity", 1)
            for _ in range(rocket_quantity):
                self.rockets.append(Rocket(self.model, rocket_config, event_bus))

        # Initialize fuel generators from config
        self.fuel_generators: List[FuelGenerator] = []
        fuel_gen_configs = config.get("fuel_generators", [])

        for fuel_gen_config in fuel_gen_configs:
            fuel_gen_quantity = fuel_gen_config.get("quantity", 1)
            for _ in range(fuel_gen_quantity):
                self.fuel_generators.append(FuelGenerator(self.model, fuel_gen_config))

        # Subscribe to events
        self.event_bus.subscribe(EventType.TRANSPORT_REQUEST.value, self.handle_transport_request)
        self.event_bus.subscribe(EventType.RESOURCE_ALLOCATED.value, self.handle_resource_allocation)

        # Initialize launch counter for metrics
        self.launches_this_step = 0

        # Hydrate from latest_state if provided
        latest_state_transportation = config.get("latest_state") if isinstance(config, dict) else None
        if latest_state_transportation:
            self._apply_latest_state(latest_state_transportation)

    def handle_transport_request(
        self, requesting_sector: str, payload: Dict[str, float], origin: str, destination: str
    ) -> None:
        """
        Handle incoming transport request from event bus.

        Args:
            requesting_sector: Sector making the request
            payload: Dictionary of resources to transport
            origin: Starting location
            destination: Target location
        """
        logger.info(f"Transportation Sector received request from {requesting_sector} for {payload}.")

        try:
            request = TransportRequest(
                requesting_sector=requesting_sector,
                payload=payload,
                origin=origin,
                destination=destination,
                status=TransportRequestStatus.QUEUED.value,
            )
            self.transport_queue.append(request)
        except ValueError as e:
            logger.error(f"Invalid transport request: {e}")

    def handle_resource_allocation(self, recipient_sector: str, resource: str, amount: float) -> None:
        """
        Receive confirmation of resource allocation from event bus.

        Args:
            recipient_sector: Sector receiving the resource
            resource: Resource type
            amount: Amount allocated
        """
        if recipient_sector == self._config.sector_name:
            if resource == "He3_kg":
                self._stocks.he3_kg += amount
                self._fuel_request_pending = False

    def _request_resources_for_fuel(self) -> None:
        """Request He3 from manufacturing sector if below threshold."""
        if (
            not self._fuel_request_pending  # Only request if no pending request
            and self._stocks.he3_kg < self._config.he3_request_threshold_kg
            and self._stocks.rocket_fuel_kg < self._config.minimum_fuel_k_sp
        ):
            self.event_bus.publish(
                EventType.RESOURCE_REQUEST.value,
                requesting_sector=self._config.sector_name,
                resource="He3_kg",  # TODO: Use enums for resouurce names
                amount=self._config.he3_request_threshold_kg,
            )
            self._fuel_request_pending = True

    def _generate_fuel(self) -> None:
        """Generate rocket fuel from He3 using fuel generators."""
        for generator in self.fuel_generators:
            if self._stocks.he3_kg > 0:
                he3_consumed, prop_generated = generator.step(self._stocks.he3_kg)
                if prop_generated > 0:
                    self._stocks.rocket_fuel_kg += prop_generated
                    self._stocks.he3_kg -= he3_consumed

    def _process_transport_queue(self) -> None:
        """Process queued transport requests and launch rockets if fuel permits."""
        # Process in reverse order (LIFO - most recent first)
        for request in reversed(self.transport_queue):
            # Find available rocket
            available_rocket = self._find_available_rocket()

            if not available_rocket:
                break  # No more available rockets

            # Attempt to launch rocket for this request
            if self._attempt_launch(available_rocket, request):
                self.transport_queue.remove(request)

    def _find_available_rocket(self) -> Optional[Rocket]:
        """Find first available rocket in fleet."""
        return next((r for r in self.rockets if r.is_available), None)

    def _attempt_launch(self, rocket: Rocket, request: TransportRequest) -> bool:
        """
        Attempt to launch rocket for given request.

        Args:
            rocket: Available rocket to launch
            request: Transport request to fulfill

        Returns:
            True if launch successful, False otherwise
        """
        # Calculate payload weights
        return_payload = request.payload
        return_payload_kg = (
            sum(return_payload.values()) * 20
        )  # TODO: Placeholder weight. This needs to change and be configurable
        outbound_payload = {}
        outbound_payload_kg = 0.0

        # Calculate fuel requirements
        flight_distance_km = (
            self._config.earth_moon_distance_km
            if self._config.earth_moon_distance_km is not None
            else get_planet_distance_km(request.origin, request.destination)
        )
        propellant_needed, one_way_steps = rocket.calculate_round_trip_requirements(
            outbound_payload_kg=outbound_payload_kg,
            return_payload_kg=return_payload_kg,
            flight_distance_km=flight_distance_km,
        )

        # Check if enough fuel available
        if propellant_needed > 0 and self._stocks.rocket_fuel_kg >= propellant_needed:
            logger.info(f"Launching rocket {rocket.unique_id} for request. " f"Fuel used: {propellant_needed:.2f} kg.")

            # Deduct fuel
            self._stocks.rocket_fuel_kg -= propellant_needed

            # Commit the launch
            rocket.commit_round_trip(
                destination=request.destination,
                origin=request.origin,
                outbound_payload=outbound_payload,
                return_payload=return_payload,
                one_way_duration=one_way_steps,
                loading_time_steps=self._config.loading_time_steps,
                requesting_sector=request.requesting_sector,
            )

            # Record successful launch for metrics
            self.launches_this_step += 1

            return True
        else:
            logger.warning(
                f"Launch of rocket {rocket.unique_id} delayed: "
                f"Not enough fuel (need {propellant_needed:.2f} kg, have {self._stocks.rocket_fuel_kg:.2f} kg)."
            )
            return False

    def _step_all_rockets(self) -> None:
        """Advance mission state for all rockets."""
        for rocket in self.rockets:
            rocket.step()

    def _serialize_mission(self, mission: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Convert rocket mission to a JSON-serializable dict."""
        if not mission:
            return None

        mission_copy = dict(mission)
        phase = mission_copy.get("phase")
        if isinstance(phase, MissionPhase):
            mission_copy["phase"] = phase.value
        return mission_copy

    def _apply_latest_state(self, t_state: Dict[str, Any]) -> None:
        """Hydrate transportation sector from latest_state snapshot."""

        # Stocks
        self._stocks.rocket_fuel_kg = float(t_state.get("rocket_fuel_kg", self._stocks.rocket_fuel_kg))
        self._stocks.he3_kg = float(t_state.get("he3_kg", self._stocks.he3_kg))
        self._fuel_request_pending = bool(t_state.get("fuel_request_pending", self._fuel_request_pending))

        # Transport queue
        queue_entries = t_state.get("transport_queue", [])
        if isinstance(queue_entries, list):
            rebuilt_queue: List[TransportRequest] = []
            for entry in queue_entries:
                try:
                    req = TransportRequest(
                        requesting_sector=entry.get("requesting_sector", ""),
                        payload=dict(entry.get("payload", {})),
                        origin=entry.get("origin", "Earth"),
                        destination=entry.get("destination", "Moon"),
                        status=entry.get("status", TransportRequestStatus.QUEUED.value),
                    )
                    rebuilt_queue.append(req)
                except Exception as exc:
                    logger.warning(f"Skipping malformed transport_queue entry during hydrate: {exc}")
            if rebuilt_queue:
                self.transport_queue = rebuilt_queue

        # Top up rockets if latest_state recorded more than config instantiated
        try:
            saved_rockets = int(t_state.get("rockets", len(self.rockets)))
            missing_rockets = saved_rockets - len(self.rockets)
            if missing_rockets > 0 and self.rocket_configs:
                base_cfg = self.rocket_configs[0]
                for _ in range(missing_rockets):
                    self.rockets.append(Rocket(self.model, base_cfg, self.event_bus))
        except Exception:
            pass

        # Top up fuel generators if latest_state recorded more than config instantiated
        try:
            saved_fuel_gens = int(t_state.get("fuel_generators", len(self.fuel_generators)))
            missing_fuel_gens = saved_fuel_gens - len(self.fuel_generators)
            if missing_fuel_gens > 0 and self.fuel_gen_configs:
                base_cfg = self.fuel_gen_configs[0]
                for _ in range(missing_fuel_gens):
                    self.fuel_generators.append(FuelGenerator(self.model, base_cfg))
        except Exception:
            pass

        # Rocket states
        rocket_states = t_state.get("rockets_state", [])
        if isinstance(rocket_states, list):
            for rocket, saved in zip(self.rockets, rocket_states):
                try:
                    rocket.is_available = bool(saved.get("is_available", rocket.is_available))
                    rocket.location = saved.get("location", rocket.location)
                    mission = saved.get("mission")
                    if mission:
                        mission_copy = dict(mission)
                        phase_val = mission_copy.get("phase")
                        if isinstance(phase_val, str):
                            mission_copy["phase"] = MissionPhase(phase_val)
                        rocket.mission = mission_copy
                    else:
                        rocket.mission = None
                except Exception as exc:
                    logger.warning(f"Skipping rocket hydrate due to error: {exc}")

    def get_power_demand(self) -> float:
        """
        Calculate total power demand from all fuel generators.

        Returns:
            Total power demand in kW
        """
        # TODO: Implement proper power demand calculation
        return 1.0

    def step(self, allocated_power: float) -> None:
        """
        Execute single simulation step for transportation sector.

        Execution Order:
        1. Generate fuel from He3
        2. Process transport queue and launch rockets
        3. Advance all rocket mission states

        Args:
            allocated_power: Power allocated to sector (currently unused)
        """
        # Reset launch counter
        self.launches_this_step = 0

        # 1. Generate Fuel
        self._request_resources_for_fuel()
        self._generate_fuel()

        # 2. Process Transport Queue and Launch Rockets
        self._process_transport_queue()

        # 3. Step All Rockets
        self._step_all_rockets()

    def _create_metric_map(self) -> dict:
        """
        Create a map of metric contributions from rocket launches.
        """
        metric_map = {}

        # Get rocket configs to find metric contribution
        if self.rocket_configs and self.launches_this_step > 0:
            # Get metric_contribution from first rocket config (same for all)
            contribution_cfg = self.rocket_configs[0].get("metric_contribution", {})
            metric_id = contribution_cfg.get("metric_id")
            value_per_launch = float(contribution_cfg.get("value", 0.0))
            if metric_id:
                metric_map[metric_id] = self.launches_this_step * value_per_launch
                logger.info(
                    f"🚀 Rocket launches: {self.launches_this_step} × {value_per_launch} = {metric_map[metric_id]} dust impact"
                )

        return metric_map

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current metrics for transportation sector.

        Returns:
            Dictionary containing stocks, rocket states, and queue status
        """
        return {
            "rockets": len(self.rockets),
            "fuel_generators": len(self.fuel_generators),
            "queued_requests": len(self.transport_queue),
            "rocket_fuel_kg": self._stocks.rocket_fuel_kg,
            "launches_this_step": self.launches_this_step,
            "he3_kg": self._stocks.he3_kg,
            "fuel_request_pending": self._fuel_request_pending,
            "transport_queue": [
                {
                    "requesting_sector": req.requesting_sector,
                    "payload": req.payload,
                    "origin": req.origin,
                    "destination": req.destination,
                    "status": req.status,
                }
                for req in self.transport_queue
            ],
            "rockets_state": [
                {
                    "is_available": rocket.is_available,
                    "location": rocket.location,
                    "mission": self._serialize_mission(rocket.mission),
                }
                for rocket in self.rockets
            ],
            "metric_contributions": self._create_metric_map(),
        }
