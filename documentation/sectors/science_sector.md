# Science Sector

**Purpose:** The `ScienceSector` orchestrates all scientific research activities within the simulation. Its primary function is to manage a fleet of `ScienceRover` agents to generate a cumulative science score, which can unlock new technologies or fulfill mission objectives.

**Core Components:**

*   **Science Rovers:** These are the primary agents within the sector. Each rover is an independent entity with its own battery, power consumption rate (`power_usage_kWh`), and science generation rate (`science_generation`). Their behavior is governed by their internal state, primarily their battery level.

**Operational Cycle (per step):**

1.  **Power Allocation:** The sector receives a total power budget from the `WorldSystem` for the current step.
2.  **Throttling:** A system-wide `throttle_factor` is applied. Each rover has a chance to be "throttled" for the step, preventing it from operating. This is a key mechanism for policies (like the Dust Coverage Policy) to influence the sector's activity level.
3.  **Rover Operation:** For un-throttled rovers, the sector distributes the available power. Each rover then executes its own `step` logic:
    *   If it has enough battery, it operates, consuming power and generating science.
    *   If it lacks power to operate, it attempts to charge from the grid, drawing from the available energy.
4.  **Metric Aggregation:** The sector aggregates the total science generated (`step_science_generated`) and power consumed by all rovers during the step.

**Interaction with the World System:**

*   **Metric Contribution:** The sector reports its contributions to system-wide metrics via the `get_metrics` method. This includes:
    *   **`IND-DUST-COV`**: The number of *operational* rovers contributes to the overall dust coverage, simulating the environmental impact of their activity.
*   **Policy Interface:** The `set_throttle_factor` method serves as a direct interface for the `PolicyEngine`. Policies can call this method to increase or decrease the sector's operational tempo in response to system-wide conditions.
*   **Dynamic Growth:** The sector listens for `module_completed` events on the event bus, allowing it to dynamically add new rovers to its fleet as they are constructed by other sectors.


## Science Sector Dynamics

### Science Metric as Technology Unlock Driver


```math
S_t = S_{t-1} + \eta_{\mathrm{SCI}} \cdot r_{\mathrm{SCI}}(t) - \delta_{\mathrm{SCI}} \, S_{t-1}
```

Unlock condition:

```math
S_t \geq S_{\mathrm{fusion}} \quad \Rightarrow \quad \text{Fusion technology unlocked}
```

**Explanation:**  
- $S_t$: cumulative science score.  
- $\eta_{\mathrm{SCI}}$: science efficiency per rover-hour/mission.  
- $r_{\mathrm{SCI}}(t)$: science rate at time \(t\).  
- $\delta_{\mathrm{SCI}}$: knowledge decay rate.  
- Crossing $S_{\mathrm{fusion}}$ unlocks helium-3 fusion tech.

