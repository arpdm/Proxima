### Construction Sector

**Purpose:** The `ConstructionSector` is the primary engine of growth for the lunar base. It manages the entire construction pipeline, from producing basic structural components to assembling complex, functional modules. It acts as a "make-to-order" factory, responding to `construction_request` events from other sectors to expand their capabilities.

**Core Components:**
*   **`PrintingRobot`:** An autonomous agent that consumes raw regolith and power to 3D print structural "shells," the basic building blocks for all modules.
*   **`AssemblyRobot`:** A more advanced agent that takes a pre-printed shell and combines it with a specific piece of equipment (e.g., a science instrument, a life support unit) to create a final, operational module.
*   **`ConstructionRequest`:** A data object that represents a single construction project, tracking its requirements (shells, equipment), its status (queued, in-progress), and the robot assigned to it.

---

### Operational Cycle & Key Algorithms

The sector operates a two-stage production line: first producing shells into a local inventory, then using those shells to fulfill construction orders.

**1. Shell Production (`_manage_printing_operations`)**
The sector employs a "make-to-stock" strategy for shells.
*   **Proactive Printing:** `PrintingRobot`s will automatically start printing new shells whenever they are idle, as long as the number of shells in local storage (`_stocks.shells`) is below the configured `shell_storage_capacity`.
*   **Resource Consumption:** Each completed shell consumes a set amount of regolith and power over a fixed number of simulation steps (`processing_time_steps`).

**2. Construction Project Lifecycle**
The core of the sector is a state machine that processes items in the `construction_queue`.

*   **A. Request (`handle_construction_request` event):**
    *   Another sector publishes a `construction_request` for a new module (e.g., a new science rover for the `ScienceSector`).
    *   The `ConstructionSector` creates a `ConstructionRequest` object and adds it to its queue in a `QUEUED` state.

*   **B. Resource Check & Acquisition (`_start_construction_project`):**
    *   For a `QUEUED` request, the sector checks if it has the necessary resources:
        1.  **Shells:** Are there enough shells in local storage?
        2.  **Equipment:** Does it have the required specialized equipment (e.g., `Science_Rover_EQ`) in its local equipment stock?
    *   **If resources are missing:**
        *   If equipment is the issue, the sector publishes a one-time `equipment_request` to the `EquipmentManSector` and waits. The project remains `QUEUED`.
        *   If shells are the issue, it simply waits for the `PrintingRobot`s to produce more.
    *   **If all resources are available:** The project proceeds.

*   **C. Assembly (`_start_construction_project` & `_advance_construction_project`):**
    *   The required shells and equipment are deducted from local inventory.
    *   An idle `AssemblyRobot` is assigned to the project, which transitions to `IN_PROGRESS`.
    *   The `AssemblyRobot` consumes power and works for a fixed number of steps (`assembly_time_steps`).

*   **D. Completion (`_advance_construction_project`):**
    *   Once the assembly timer finishes, the robot becomes `IDLE` again.
    *   The project is marked as `COMPLETED` and removed from the queue.
    *   Crucially, the sector publishes a `module_completed` event, signaling to the original requesting sector that its new module is ready.

---

### Configuration Options

The sector's capabilities are defined in the `world_system` JSON file, specifying the number of robots and operational parameters.

```json
"construction": {
  "sector_name": "construction",
  "max_concurrent_projects": 3,
  "shell_storage_capacity": 10,
  "printing_robots": [
    {
      "quantity": 2,
      "max_power_usage_kWh": 65,
      "processing_time_t": 80,
      "regolith_usage_kg": 200
    }
  ],
  "assembly_robots": [
    {
      "quantity": 2,
      "max_power_usage_kWh": 50,
      "assembly_time_t": 60
    }
  ]
}
```

---

### TODO: Potential Improvements

*   **[ ] Implement Power Throttling:** The sector receives `allocated_power` but does not currently use it to manage robot activity. If power is insufficient, robots should be throttled or enter a low-power state instead of operating at full capacity.
*   **[ ] Add Metric Contributions:** Construction is a heavy industrial activity. Both printing and assembly should contribute to the `IND-DUST-COV` metric based on the number of active robots.
*   **[ ] Centralize Equipment Mapping:** The `EQUIPMENT_MAP` is hardcoded within the class. This should be loaded from a central configuration file to make adding new equipment types easier.
*   **[ ] Implement Dynamic Growth:** The sector should listen for `module_completed` events for `Printing_Robot_EQ` and `Assembly_Robot_EQ` to dynamically add new robots to its fleet.
*   **[ ] Add Resource Constraints for Printing:** `PrintingRobot`s currently have an infinite supply of regolith. They should request and consume it from the `ManufacturingSector`.

<!-- ... code... -->