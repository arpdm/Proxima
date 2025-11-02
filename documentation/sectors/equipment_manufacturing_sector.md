### Equipment Manufacturing Sector

**Purpose:** The `EquipmentManSector` acts as the central logistics hub for heavy equipment on the Moon. Despite its name, its primary role in the current implementation is not manufacturing, but rather managing the inventory of critical assets like rovers and robots. It ensures that other sectors have the equipment they need to operate and expand by managing stock levels and orchestrating resupply missions from Earth.

**Core Components & Data Structures:**
*   **`EquipmentInventory`:** The heart of the sector, this class tracks the lifecycle of all equipment.
    *   `physical_stock`: The quantity of equipment physically present and available for allocation on the Moon.
    *   `pending_orders`: The quantity of equipment that has been requested from Earth but has not yet arrived.
*   **`_equipment_backlog`:** A queue (`deque`) that holds unfulfilled equipment requests from other sectors. If a request cannot be met due to insufficient stock, it remains in the backlog to be re-evaluated in the next step.
*   **`_event_buffer`:** A temporary list that collects all incoming events during a simulation step, ensuring they are processed in a controlled manner at the start of the next step.

---

### Operational Cycle & Key Algorithms

The sector's logic is event-driven and revolves around maintaining minimum stock levels.

**1. Event Processing (`_process_buffered_events`)**
At the start of each step, the sector processes all events that have arrived since the last step.
*   **`payload_delivered`:** When a resupply mission from Earth arrives, the sector updates its inventory:
    *   Increases `physical_stock` with the delivered items.
    *   Decreases `pending_orders` by the same amount, as the order is now fulfilled.
*   **`equipment_request`:** When another sector requests equipment, the request is added to the `_equipment_backlog` to be processed.

**2. Fulfilling Requests (`_process_equipment_backlog`)**
The sector attempts to fulfill pending requests from its `physical_stock`.
*   If stock is sufficient, it publishes an `equipment_allocated` event (notifying the requesting sector) and deducts the items from its inventory.
*   If stock is insufficient, the request remains in the backlog, and the sector will try to fulfill it again in a future step once new stock arrives.

**3. Proactive Resupply Logic (`_check_and_request_resupply`)**
This is the core algorithm that prevents equipment shortages.
*   **Calculate Effective Stock:** For each equipment type, it calculates the `effective_stock`. This is the crucial insight of the sector's logic.
    ```math
    \text{Stock}_{\text{effective}} = \text{Stock}_{\text{physical}} + \text{Orders}_{\text{pending}}
    ```
*   **Check Against Minimums:** It compares this `effective_stock` against a pre-configured `minimum_level`.
*   **Request Resupply:** If the effective stock is below the minimum, it calculates the deficit and immediately takes two actions:
    1.  It publishes a `transport_request` event, asking the `TransportationSector` to launch a resupply mission from Earth with the required equipment.
    2.  It immediately increases its own `pending_orders` for the requested amount. This is critical as it prevents the sector from sending duplicate resupply requests in subsequent steps for items that are already in transit.

---

### Configuration Options

The sector is configured in the `world_system` JSON file. You can set initial inventory levels and define the minimum stock thresholds that trigger the resupply logic.

```json
"equipment_manufacturing": {
  "sector_name": "equipment_manufacturing",
  "initial_stocks": {
    "Science_Rover_EQ": 2,
    "Assembly_Robot_EQ": 1
  },
  "minimum_levels": {
    "Science_Rover_EQ": 3,
    "Assembly_Robot_EQ": 2,
    "ISRU_Robot_EQ": 2
  }
}
```
