from mesa import Agent
from typing import Dict, Optional, Tuple


class Rocket(Agent):
    """
    Represents a reusable rocket for transporting payloads between locations.

    The rocket has a specific carrying capacity and propellant efficiency. It can
    be launched on missions, during which it becomes unavailable. The `step` method
    simulates the passage of time, and upon arrival, the rocket delivers its
    payload and becomes available again.
    """

    def __init__(self, model, agent_config: dict, event_bus):
        """
        Initializes a Rocket agent.

        Args:
            model: The model instance the agent belongs to.
            agent_config (dict): Agent-specific configuration.
        """
        super().__init__(model)

        config = agent_config.get("config", agent_config)
        self.event_bus = event_bus
        self.config = config

        # Physical characteristics
        self.prop_usage_kg_per_payload_kg = float(config.get("prop_usage_kg_per_payload_kg", 21.4))
        self.carrying_capacity_kg = float(config.get("carrying_capacity_equipment", 22800))
        self.max_speed_km_h = float(config.get("max_speed_km_h", 5300))

        # State variables
        self.is_available = True
        self.location = config.get("initial_location", "Earth")
        self.mission: Optional[Dict] = None

    def calculate_round_trip_requirements(
        self, outbound_payload_kg: float, return_payload_kg: float, flight_distance_km: int
    ) -> Tuple[float, int]:
        """
        Calculates the fuel and time required for a round trip without launching.

        Returns:
            A tuple of (total_propellant_needed, one_way_steps).
            Returns (0.0, 0) if the payload exceeds capacity.
        """
        if outbound_payload_kg > self.carrying_capacity_kg or return_payload_kg > self.carrying_capacity_kg:
            return 0.0, 0

        propellant_outbound = outbound_payload_kg * self.prop_usage_kg_per_payload_kg
        propellant_return = return_payload_kg * self.prop_usage_kg_per_payload_kg
        total_propellant_needed = propellant_outbound + propellant_return
        trip_duration_hours = int(flight_distance_km / self.max_speed_km_h)
        return total_propellant_needed, trip_duration_hours

    def commit_round_trip(
        self,
        destination: str,
        origin: str,
        outbound_payload: Dict,
        return_payload: Dict,
        one_way_duration: int,
        loading_time_steps: int,
        requesting_sector: str
    ):
        """
        Commits the rocket to a pre-calculated round trip mission, changing its state.
        This should only be called after confirming resource availability.
        """
        if not self.is_available:
            return  # Should not happen if logic is correct

        self.is_available = False
        self.mission = {
            "origin": origin,
            "destination": destination,
            "phase": "outbound",  # Phases: outbound, loading, inbound
            "outbound_payload": outbound_payload,
            "return_payload": return_payload,
            "eta_steps": one_way_duration,
            "one_way_duration": one_way_duration,
            "loading_duration": loading_time_steps,
            "requesting_sector": requesting_sector
        }

    def step(self) -> tuple:
        """
        Executes one step of the rocket's simulation, progressing its mission.
        This method functions as a state machine for the rocket's mission phases.
        """

        if not self.mission:
            return

        # Decrement ETA for the current phase
        self.mission["eta_steps"] -= 1
        
        # Check for phase completion
        if self.mission["eta_steps"] <= 0:
            # --- OUTBOUND ARRIVAL ---
            if self.mission["phase"] == "outbound":
                print(f"Rocket arrived at {self.mission['destination']}. Unloading payload.")
                self.location = self.mission["destination"]
                self.mission["phase"] = "loading"
                self.mission["eta_steps"] = self.mission["loading_duration"]

                # Publish event for payload delivery
                self.event_bus.publish(
                    "payload_delivered",
                    to_sector=self.mission["requesting_sector"],
                    payload=self.mission["outbound_payload"],
                )

            # --- LOADING COMPLETE ---
            elif self.mission["phase"] == "loading":
                print(f"Rocket finished loading at {self.mission['destination']}. Launching return trip.")
                self.location = "In-Transit (Inbound)"
                self.mission["phase"] = "inbound"
                self.mission["eta_steps"] = self.mission["one_way_duration"]

            # --- INBOUND ARRIVAL (Round Trip Complete) ---
            elif self.mission["phase"] == "inbound":
                print(f"Rocket has returned to {self.mission['origin']}. Mission complete.")
                self.location = self.mission["origin"]
                self.is_available = True
                # Publish event for return payload delivery
                self.event_bus.publish(
                    "payload_delivered",
                    to_sector=self.mission["requesting_sector"],
                    payload=self.mission["return_payload"],
                )
                self.mission = None  # Clear mission, rocket is now idle

    def report(self) -> dict:
        """
        Generates a dictionary reporting the current state of the rocket.
        """
        return {"is_available": self.is_available, "location": self.location, "mission": self.mission, "type": "rocket"}
