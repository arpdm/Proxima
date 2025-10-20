from typing import List, Dict
from proxima_model.components.rocket import Rocket
from proxima_model.components.fuel_generator import FuelGenerator


class TransportationSector:

    # Constants for the simulation
    # TODO: This can be loaded to enviornment configuration
    EARTH_MOON_DISTANCE_KM = 384400
    LOADING_TIME_STEPS = 24  # e.g., 24 hours

    def __init__(self, model, config: dict, event_bus):
        self.model = model
        self.event_bus = event_bus
        self.transport_queue: List[Dict] = []

        # Internal buffer for resources needed for fuel production
        self.internal_stocks = {"He3_kg": 0.0}

        self.stocks = {"rocket_fuel_kg": 0.0}

        # Initialize rocket fleet
        self.rockets: List[Rocket] = []
        for i, rocket_cfg in enumerate(config.get("rockets", [])):
            self.rockets.append(Rocket(self.model, rocket_cfg, event_bus))

        # Initialize fuel generators
        self.fuel_generators: List[FuelGenerator] = []
        for gen_cfg in config.get("fuel_generators", []):
            self.fuel_generators.append(FuelGenerator(gen_cfg))

        # Subscribe to events
        self.event_bus.subscribe("transport_request", self.handle_transport_request)
        self.event_bus.subscribe("resource_allocated", self.handle_resource_allocation)

    def handle_transport_request(self, requesting_sector: str, payload: dict, origin: str, destination: str):
        """This method is called automatically by the event bus to queue a new request."""

        print(f"Transportation Sector received request from {requesting_sector} for {payload}.")

        self.transport_queue.append(
            {
                "requesting_sector": requesting_sector,
                "payload": payload,
                "origin": origin,
                "destination": destination,
                "status": "queued",
            }
        )

    def handle_resource_allocation(self, recipient_sector: str, resource: str, amount: float):
        """Receives confirmation that a requested resource has been allocated."""
        if recipient_sector == "transportation":
            print(f"Transportation Sector received allocation of {amount} kg of {resource}.")
            if resource in self.internal_stocks:
                self.internal_stocks[resource] += amount

    def _request_resources_for_fuel(self):
        """Checks internal He3 stock and requests more if below a threshold."""
        if self.internal_stocks["He3_kg"] < 1:
            self.event_bus.publish("resource_request", requesting_sector="transportation", resource="He3_kg", amount=1)

    def get_power_demand(self) -> float:
        """Calculate the total power demand from all fuel generators."""
        # TODO: This will need to change later
        return 1

    def step(self, allocated_power):
        """
        Executes a single simulation step for the transportation sector.

        Execution Order:
        1. Generate fuel.
        2. Process the transport queue and launch available rockets if fuel permits.
        3. Step each rocket to advance its mission state.
        """

        # 1. Generate Fuel
        self._request_resources_for_fuel()

        for generator in self.fuel_generators:
            if self.internal_stocks["He3_kg"] > 0:
                he3_consumed, prop_generated = generator.step(self.internal_stocks["He3_kg"])
                if prop_generated > 0:
                    self.stocks["rocket_fuel_kg"] += prop_generated
                    self.internal_stocks["He3_kg"] -= he3_consumed

        # 2. Process Transport Queue and Launch Rockets
        for request in reversed(self.transport_queue):
            available_rocket = next((r for r in self.rockets if r.is_available), None)

            if available_rocket:
                # This logic now correctly handles Earth -> Moon requests
                return_payload = request["payload"]
                return_payload_kg = sum(return_payload.values()) * 20  # Placeholder weight
                outbound_payload = {}
                outbound_payload_kg = 0.0

                # STEP 1: CALCULATE requirements without changing rocket state
                propellant_needed, one_way_steps = available_rocket.calculate_round_trip_requirements(
                    outbound_payload_kg=outbound_payload_kg,
                    return_payload_kg=return_payload_kg,
                    flight_distance_km=self.EARTH_MOON_DISTANCE_KM,
                )

                print("Prop Needed: ", propellant_needed)

                # STEP 2: CHECK resources BEFORE committing
                if propellant_needed > 0 and self.stocks["rocket_fuel_kg"] >= propellant_needed:
                    print(
                        f"Launching rocket {available_rocket.unique_id} for request. Fuel used: {propellant_needed:.2f} kg."
                    )
                    self.stocks["rocket_fuel_kg"] -= propellant_needed

                    # STEP 3: COMMIT the launch now that fuel is secured
                    available_rocket.commit_round_trip(
                        destination="Earth",
                        outbound_payload=outbound_payload,
                        return_payload=return_payload,
                        one_way_duration=one_way_steps,
                        loading_time_steps=self.LOADING_TIME_STEPS,
                    )

                    self.transport_queue.remove(request)
                else:
                    # This message is now accurate, as the rocket's state has not changed.
                    print(f"Launch of rocket {available_rocket.unique_id} delayed: Not enough fuel.")
            else:
                break

        # 3. Step All Rockets
        for rocket in self.rockets:
            rocket.step()

    def get_metrics(self) -> dict:
        """Returns current metrics for the transportation sector."""
        return {
            "stocks": self.stocks.copy(),
            "rockets": [r.report() for r in self.rockets],
            "queued_requests": len(self.transport_queue),
        }
