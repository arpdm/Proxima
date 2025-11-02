# Transportation Sector

**Purpose:** The `TransportationSector` is the logistics backbone of the simulation, managing the entire lifecycle of interplanetary transport. It orchestrates a fleet of reusable rockets, handles the production of rocket fuel from local resources (Helium-3), and processes transport requests to move equipment and materials between Earth and the Moon.

**Core Components:**
*   **`Rocket`:** A reusable agent capable of round-trip missions. Each rocket has a specific payload capacity and fuel efficiency. Its internal state machine manages its availability and mission progress (outbound flight, loading on the Moon, inbound flight).
*   **`FuelGenerator`:** An agent that simulates an advanced fusion-based reactor. It consumes Helium-3 (`He3_kg`) to generate power, which is then used to produce rocket propellant.
*   **`TransportRequest`:** A data object representing a single logistics mission, detailing the payload, origin, destination, and requesting sector.

---

### Operational Cycle & Key Algorithms

The sector's operation is a continuous loop of fuel production, request processing, and mission management.

**1. Fuel Production Pipeline**
The sector aims to be self-sufficient by producing its own fuel.
*   **A. Proactive He-3 Request (`_request_resources_for_fuel`):** If the sector's internal stock of rocket fuel and He-3 fall below configured minimums, it automatically publishes a `resource_request` to the event bus to acquire more He-3. This ensures a steady supply of raw material for fuel generation.
*   **B. Fuel Generation (`_generate_fuel`):** In every step, the sector tasks its `FuelGenerator`s to convert available He-3 into rocket fuel, which is added to its `rocket_fuel_kg` stock.

**2. Launch Processing (`_process_transport_queue`)**
The sector processes pending transport requests in a Last-In-First-Out (LIFO) order.
*   **A. Find Available Rocket:** It scans its fleet for a `Rocket` that is currently `is_available`.
*   **B. Pre-Launch Calculation (`_attempt_launch`):** For an available rocket and a pending request, it performs a critical check:
    1.  It calculates the total propellant required for a round trip based on the payload mass.
    2.  It compares the required fuel against its current `rocket_fuel_kg` stock.
*   **C. Launch or Defer:**
    *   **If fuel is sufficient:** The rocket is launched. The required fuel is deducted from the sector's stock, and the rocket's `commit_round_trip` method is called. The rocket becomes unavailable, and its internal mission timer begins.
    *   **If fuel is insufficient:** The launch is deferred. The request remains in the queue, and the sector will attempt to launch it again in a future step once more fuel has been generated.

**3. Mission Progression (`_step_all_rockets`)**
In every simulation step, the sector calls the `step()` method on every rocket in its fleet.
*   This advances the internal state machine of any rocket currently on a mission.
*   When a rocket arrives at its destination (either the Moon or Earth), it publishes a `payload_delivered` event, notifying the relevant sector that its requested equipment or resources have arrived.
*   Upon returning to its origin, the rocket's mission is cleared, and it becomes `is_available` for a new task.

---

### Equations

**Fuel Generation:**
The amount of propellant generated $P_{\text{gen}}$ from a given amount of Helium-3 $He3_{\text{proc}}$ is calculated as:

```math
\text{kWh}_{\text{avail}} = (He3_{\text{proc}} \times \text{GWh}_{\text{thermal}} \times 10^6) \times \eta_{\text{efficiency}}
```

```math
P_{\text{gen}} = \frac{\text{kWh}_{\text{avail}}}{\text{kWh}_{\text{per\_kg\_prop}}}
```

Where:
*   $\text{GWh}_{\text{thermal}}$ is the thermal energy per kg of He-3.
*   $\eta_{\text{efficiency}}$ is the generator's conversion efficiency.
*   $\text{kWh}_{\text{per\_kg\_prop}}$ is the energy needed to create 1 kg of propellant.

**Rocket Fuel Calculation:**

The propellant needed for a round trip $P_{\text{total}}$ is the sum of the outbound and return legs.

```math
P_{\text{outbound}} = \text{Payload}_{\text{outbound\_kg}} \times \text{Usage}_{\text{prop\_per\_kg}}
```

```math
P_{\text{return}} = \text{Payload}_{\text{return\_kg}} \times \text{Usage}_{\text{prop\_per\_kg}}
```

```math
P_{\text{total}} = P_{\text{outbound}} + P_{\text{return}}
```

---

### Configuration Options

The sector is configured in the `world_system` JSON file, defining its fleet, fuel generators, and operational parameters.

```json
"transportation": {
  "sector_name": "transportation",
  "earth_moon_distance_km": 384400,
  "loading_time_steps": 24,
  "he3_request_threshold_kg": 1.0,
  "minimum_fuel_k_sp": 5000,
  "rockets": [
    {
      "template_id": "comp_rocket",
      "quantity": 3,
      "config": {
        "prop_usage_kg_per_payload_kg": 21.4,
        "carrying_capacity_equipment": 22800
      },
      "metric_contributions": [
        { "metric_id": "IND-DUST-COV", "value": 0.1 }
      ]
    }
  ],
  "fuel_generators": [
    {
      "template_id": "comp_fuel_gen_rocket",
      "quantity": 1
    }
  ]
}
```

---

### TODO: Potential Improvements

*   **[ ] Implement Realistic Power Demand:** The `get_power_demand()` method is a placeholder. The `FuelGenerator`s should consume significant power from the grid when operating.
*   **[ ] Refine Payload Weight Calculation:** The weight for return payloads is currently a placeholder (`sum(values) * 20`). This should be replaced with a data-driven model that maps equipment types to their actual mass.
*   **[ ] Implement Queue Prioritization:** The transport queue is processed Last-In-First-Out (LIFO). A more robust system would allow for request prioritization based on urgency or the importance of the payload.
*   **[ ] Standardize Metric Contributions:** The metric contribution logic should be updated to use the plural `metric_contributions` and handle a list of contributions, consistent with other sectors.
*   **[ ] Add Dynamic Fleet Expansion:** The sector should listen for `module_completed` events to dynamically add new rockets and fuel generators to its fleet as they are constructed.