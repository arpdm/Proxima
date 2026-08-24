# Transportation Sector

**Purpose:** The `TransportationSector` is the logistics backbone of the simulation, managing the entire lifecycle of interplanetary transport. It orchestrates a fleet of reusable rockets, handles the production of rocket fuel from local resources (Helium-3), and processes transport requests to move equipment and materials between Earth and the Moon.

**Core Components:**
*   **`Rocket`:** A reusable agent capable of round-trip missions. Each rocket has a specific payload capacity and fuel efficiency. Its internal state machine manages its availability and mission progress (outbound flight, loading on the Moon, inbound flight).
*   **`FuelGenerator`:** An agent that converts Helium-3 (`He3_kg`) into rocket propellant. The He-3 thermal energy determines propellant output; the generator's grid demand is configured separately.
*   **`TransportRequest`:** A data object representing a single logistics mission, detailing the payload, origin, destination, and requesting sector.

---

## Operational Cycle & Key Algorithms

The sector's operation is a continuous loop of fuel production, request processing, and mission management.

**1. Fuel Production Pipeline**
The sector aims to be self-sufficient by producing its own fuel.
*   **A. Proactive He-3 Request (`_request_resources_for_fuel`):** If the sector's internal stock of rocket fuel and He-3 fall below configured minimums, it automatically publishes a `resource_request` to the event bus to acquire more He-3. This ensures a steady supply of raw material for fuel generation.
*   **B. Fuel Generation (`_generate_fuel`):** In every step, the sector tasks its `FuelGenerator`s to convert available He-3 into rocket fuel, which is added to its `rocket_fuel_kg` stock. Each generator's output is gated by the grid power it's actually allocated for the step (see **Power-Gated Operation** below).

**1.1 Power-Gated Operation**
`FuelGenerator`s don't get to consume power for free — like every other power-consuming sector, `TransportationSector` reports a power demand each step and only produces fuel with whatever power the `EnergySector` actually allocates back to it.
*   **A. Demand Reporting (`get_power_demand`):** Before allocation, the sector sums each generator's `get_power_demand()` — the configured `power_demand_kWh_per_step`, scaled down if there isn't enough He-3 on hand to run a full step.
*   **B. Allocation:** `WorldSystem.step()` collects demand from every power-consuming sector, and `EnergySector.allocate_power()` returns each sector's share for the step. This may be less than what was demanded if power is scarce.
*   **C. Throttled Generation (`_generate_fuel` → `FuelGenerator.step`):** The sector hands its `allocated_power` to its generators one at a time, in order, each drawing from whatever power remains:
    1.  A generator's usable power is `min(allocated_power_remaining, its own power_demand)`.
    2.  If usable power is less than its demand, the generator is `is_throttled` and scales down He-3 consumption and propellant output by the same fraction (`power_fraction = usable_power / power_demand`).
    3.  If usable power is `0`, the generator produces nothing this step (`is_operational = False`).
    4.  Remaining power after each generator feeds into the next, so a shortfall only throttles generators once earlier ones have taken their share.
*   **D. Metrics:** The sector tracks `power_demand_step`, `power_consumed_step`, and `fuel_generators_throttled_this_step` each step for visibility into how much of its demand was actually met.

```{mermaid}
flowchart LR
    A["Report power demand<br/>(get_power_demand)"] --> B["EnergySector allocates power<br/>(allocate_power)"]
    B --> C["Generators consume allocated power<br/>(_generate_fuel)"]
    C --> D["Fuel produced, throttled if<br/>power fell short of demand"]
```

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

## Equations

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

**Fuel Generator Grid Demand:**
The generator's grid energy demand is not derived from He-3 thermal energy. A full generator step uses the configured `power_demand_kWh_per_step`; if less He-3 is available, demand scales with the fraction of the step that can run.

```math
\text{Energy}_{\text{demand}} =
\text{Energy}_{\text{configured}} \times
\frac{He3_{\text{proc}}}{He3_{\text{max\_per\_step}}}
```

**Usable Power & Throttling:**
Each generator draws from whatever power remains after earlier generators have taken their share. Its usable power is capped by both what's left and its own demand:

```math
\text{Power}_{\text{usable}} = \max\left(0, \min\left(\text{Power}_{\text{remaining}}, \text{Energy}_{\text{demand}}\right)\right)
```

The fraction of demand actually met determines how much the generator's He-3 consumption and propellant output are scaled down:

```math
f_{\text{power}} = \frac{\text{Power}_{\text{usable}}}{\text{Energy}_{\text{demand}}}
```

```math
He3_{\text{consumed}} = He3_{\text{proc}} \times f_{\text{power}}
```

A generator is `is_throttled` whenever $f_{\text{power}} < 1$, and produces nothing ($f_{\text{power}} = 0$) when no power remains.

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

## Configuration Options

The sector is configured in the `world_system` JSON file, defining its fleet, fuel generators, and operational parameters. If `flight_distance` is omitted, the sector uses the shared `FLIGHT_DISTANCE_KM` lookup table in `world_system_defs.py`.

```json
"transportation": {
  "sector_name": "transportation",
  "flight_distance": 384400,
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
        {
          "metric_id": "IND-DUST-COV",
          "contribution_type": "predefined",
          "contribution_value": 0.1
        }
      ]
    }
  ],
  "fuel_generators": [
    {
      "template_id": "comp_fuel_gen_rocket",
      "quantity": 1,
      "config": {
        "efficiency": 0.5,
        "thermal_GWh_per_kg": 163.9,
        "kwh_per_kg_prop": 22.8,
        "power_demand_kWh_per_step": 65,
        "he3_kg_per_hour": 5
      }
    }
  ]
}
```

## Improvement Areas

*  **Implement Queue Prioritization:** The transport queue is processed Last-In-First-Out (LIFO). A more robust system would allow for request prioritization based on urgency or the importance of the payload.
