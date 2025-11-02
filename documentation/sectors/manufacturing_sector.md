# Manufacturing Sector

**Purpose:** The `ManufacturingSector` manages all In-Situ Resource Utilization (ISRU) operations on the lunar base. It orchestrates a fleet of unified ISRU robots to produce essential resources like Helium-3, water, and metals. The sector operates as an intelligent, demand-driven factory, automatically prioritizing tasks based on the current stock levels of critical resources and fulfilling requests from other sectors.

**Core Components:**
*   **`ISRUAgent`:** A versatile agent that can be configured to perform various tasks, including ice extraction, regolith processing, and Helium-3 generation. Each mode has distinct power requirements and resource outputs.
*   **`BufferTarget`:** A data object that defines the desired inventory level for a specific resource, with `min` and `max` thresholds. These targets drive the sector's entire decision-making process.
*   **`TaskDefinition`:** Maps an abstract task (e.g., `TaskType.WATER`) to a specific `ISRUAgent` operational mode (e.g., `ICE_EXTRACTION`) and its primary resource output.
*   **`StockFlow`:** A transaction object that represents any change in resources. It ensures that all resource generation, consumption, and allocation within a single step are processed atomically, preventing race conditions and ensuring data integrity.
*   **`ResourceRequest`:** A data object representing a request for a specific amount of a resource from another sector.

---

### Operational Cycle & Key Algorithms

The sector's logic is a sophisticated loop of assessing needs, assigning tasks, and processing results.

**A. Deficiency-Driven Task Prioritization (`_calculate_task_priorities`)**
This is the core decision-making algorithm. At the start of each step, the sector determines which resources are most needed.

*   For each resource with a defined `BufferTarget`, it calculates the `deficiency`.
    ```math
    \text{Deficiency} = \max(0, \text{Target}_{\min} - \text{Stock}_{\text{current}})
    ```
*   It then creates a prioritized list of tasks, ordered from the largest deficiency to the smallest. This ensures that robots are always working on the most critical shortfall.

**B. Task Assignment (`_assign_agents_to_tasks`)**

With a prioritized task list, the sector assigns its available `ISRU` robots.
*   It iterates through the priority list and assigns one idle robot to each task until it runs out of robots.
*   The robot's operational mode is set according to the task definition (e.g., a "WATER" task sets the robot's mode to `ICE_EXTRACTION`).

**C. Resource Request Fulfillment (`_process_buffered_resource_requests`)**

The sector manages an incoming queue of `ResourceRequest` events from other sectors.
*   It checks if the current stock is sufficient to fulfill a pending request.
*   If yes, it creates a `StockFlow` transaction to deduct the resource from its inventory and allocate it to the requesting sector. An event is then published to notify the recipient.
*   If no, the request remains in the queue to be re-evaluated in the next step.

**D. Probabilistic Throttling & Operation**

When executing the step, the sector can be throttled by the `PolicyEngine`.
*   For each robot, a random number is checked against the `robot_throttle` factor. If the number is less than the factor, the robot is marked as `THROTTLED` and skips its operation for that step.
*   If a robot is not throttled and has enough allocated power, it performs its operation, which generates a `StockFlow` object detailing the resources produced.

**E. Atomic Stock Flow Processing (`process_all_stock_flows`)**

At the end of the step, all `StockFlow` objects generated during the step (from robot operations and resource allocations) are processed in a single, atomic block. This guarantees that all additions and subtractions to the resource stocks are finalized before the next simulation step begins.

---

### Equations

**He-3 Generation:**
The amount of Helium-3 generated $He3_{\text{output}}$ is calculated using a probabilistic concentration and the robot's throughput.

```math
C_{\text{He3}} = \text{random.triangular}(\text{min}_{\text{ppb}}, \text{mode}_{\text{ppb}}, \text{max}_{\text{ppb}})
```

```math
He3_{\text{output}} = (\text{Throughput}_{\text{tons}} \times 1000) \times (C_{\text{He3}} \times 10^{-9}) \times \eta_{\text{efficiency}}
```

Where:
*   $C_{\text{He3}}$ is the randomly determined concentration in parts-per-billion for that step.
*   $\text{Throughput}_{\text{tons}}$ is the mass of regolith the robot can process per step.

---

### Configuration Options

The sector is configured in the `world_system` JSON file, defining its robot fleet, initial stocks, and resource targets.

```json
"manufacturing": {
  "sector_name": "manufacturing",
  "initial_stocks": {
    "H2O_kg": 5.0,
    "He3_kg": 10.0
  },
  "buffer_targets": {
    "He3_kg": { "min": 20.0, "max": 300.0 },
    "H2O_kg": { "min": 2.0, "max": 10.0 }
  },
  "isru_robots": [
    {
      "quantity": 4,
      "config": {
        "ice_extraction_power_kWh": 5.0,
        "ice_extraction_output_kg": 20.0,
        "regolith_extraction_power_kWh": 10.0,
        "he3_extraction_power_kWh": 50.0
      },
      "metric_contributions": [
        {
          "metric_id": "IND-DUST-COV",
          "contribution_type": "predefined",
          "contribution_value": 0.01
        }
      ]
    }
  ]
}
```

---

### TODO: Potential Improvements

*   **[ ] Implement Electrolysis:** The `TaskType.ELECTROLYSIS` exists but is not implemented. This would be a crucial task, consuming `H2O_kg` and power to produce `H2_kg` and `O2_kg`.
*   **[ ] Add Resource Consumption for Extraction:** The `ICE_EXTRACTION` and `REGOLITH_EXTRACTION` modes currently create resources from nothing. They should consume a base resource (e.g., "Raw_Regolith") to be more realistic.
*   **[ ] Implement Metal Production:** The `TaskType.METAL` exists but is not implemented. This would involve processing `FeTiO3_kg` (Ilmenite) to produce `Fe_kg`, `Ti_kg`, and `O2_kg`.
*   **[ ] Add Dynamic Fleet Expansion:** The sector should listen for `module_completed` events for `ISRU_Robot_EQ` to dynamically add new robots to its fleet.
*   **[ ] Refine Task Assignment Logic:** The current assignment is simple (one robot per task). A more advanced system could assign multiple robots to a single high-priority task or consider robot specialization if different `ISRU` agents have different efficiencies.