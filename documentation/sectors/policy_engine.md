# Policy Engine

**Purpose:** The `PolicyEngine` is the adaptive "brain" of the simulation. It centralizes the logic for enforcing operational rules and adaptive behaviors. It continuously monitors the simulation's performance via the `EvaluationEngine` and applies corrective actions—or "policies"—to steer the system towards its defined goals.

---

### Architecture

The engine is designed to be modular and extensible, revolving around three key concepts:

1.  **`PolicyEngine`:** The central manager class. Its primary responsibilities are:
    *   Maintaining a registry of all available policies.
    *   Iterating through all *enabled* policies during each simulation step.
    *   Calling the `apply` method on each policy, providing it with the latest simulation performance data.
    *   Collecting the results (or "effects") of each policy application for logging and analysis.

2.  **`Policy` Protocol:** This is the core contract defined in `policy_protocol.py`. For an object to be considered a policy, it must conform to this protocol, which requires it to have:
    *   `id`: A unique string identifier (e.g., `PLCY-ENV-DUST-THROTTLE`).
    *   `name`: A human-readable name.
    *   `enabled`: A boolean flag to easily turn the policy on or off.
    *   `apply(engine, evaluation_result)`: The main method containing the policy's logic.

3.  **`EvaluationResult`:** This is the sole input for the policy engine's decision-making process. It is a comprehensive data object provided by the `EvaluationEngine` that contains the final scores and metric values for the current simulation step. The `PolicyEngine` does not perform calculations; it **reacts** to the data in this object.

---

### Operational Flow

The policy application process is a clear, sequential part of the main simulation loop.

1.  **Input:** After the `WorldSystem` has stepped all sectors and the `EvaluationEngine` has calculated all scores, the `WorldSystem` calls `policy_engine.apply_policies()`, passing the final `EvaluationResult`.
2.  **Iteration:** The `PolicyEngine` loops through its internal list of registered policies.
3.  **Execution:** For each policy where `enabled` is `True`, it calls that policy's `apply()` method.
4.  **Logic:** Inside the `apply()` method, the policy inspects the `evaluation_result` to check the status of relevant metrics. For example, the `DustCoverageThrottlePolicy` checks the score for the `IND-DUST-COV` metric.
5.  **Action:** If a condition is met, the policy takes action by calling a method on one of the sectors. It can access any sector via the `engine.world` object passed into the `apply` method (e.g., `engine.world.sectors['science'].set_throttle_factor(0.5)`).
6.  **Output:** The `apply()` method returns a dictionary summarizing the actions it took (its "effects"). The `PolicyEngine` collects these effects from all active policies and returns them to the `WorldSystem` for logging.

---

### How to Create a New Policy

Adding a new policy is a straightforward process designed to be self-contained.

#### Step 1: Define the Policy Class

Create a new class that implements the `Policy` protocol. For this example, we'll create a policy that throttles science activity if there is a power shortage.

```python
# In a file like /proxima_model/policy_engine/economic_policies.py

from __future__ import annotations
from typing import Dict, Any, TYPE_CHECKING
import logging

# ... (TYPE_CHECKING imports) ...

logger = logging.getLogger(__name__)

class PowerShortageContingencyPolicy:
    """
    Reduces science activity if there is a power shortage to preserve
    power for essential systems.
    """
    id = "PLCY-ECON-POWER-CONTINGENCY"
    name = "Power Shortage Contingency"
    enabled = True

    def apply(self, engine: "PolicyEngine", evaluation_result: "EvaluationResult") -> Dict[str, Any]:
        """Apply the power shortage policy."""
        
        # 1. Find the relevant metric score
        power_metrics = evaluation_result.performance_metrics
        power_shortage = power_metrics.get("PWR-SHORTAGE-KW", 0.0)

        effects = {"power_shortage_detected_kw": power_shortage, "throttle_applied": "none"}

        # 2. Apply logic
        if power_shortage > 0:
            # 3. Take action by calling a method on a sector
            throttle_factor = 0.8 # Drastically reduce science activity
            engine.world.sectors['science'].set_throttle_factor(throttle_factor)
            
            effects["throttle_applied"] = "science"
            effects["new_throttle_factor"] = throttle_factor
            logger.warning(f"⚠️ {self.name}: Power shortage of {power_shortage:.2f} kW detected. Throttling science sector.")
        else:
            # Ensure throttle is reset if conditions are normal
            engine.world.sectors['science'].set_throttle_factor(0.0)

        return effects
```

#### Step 2: Register the New Policy

In `policy_engine.py`, import your new policy class and add an instance of it to the `_policies` list in the `__init__` method.

```python
# /proxima_model/policy_engine/policy_engine.py
# ... (existing imports) ...
from proxima_model.policy_engine.environmental_policies import DustCoverageThrottlePolicy
from proxima_model.policy_engine.science_policies import ScienceProductionRate
from proxima_model.policy_engine.economic_policies import PowerShortageContingencyPolicy # <-- IMPORT

class PolicyEngine:
    # ...
    def __init__(self, world):
        self.world = world
        self._policies: List[Policy] = [
            DustCoverageThrottlePolicy(), 
            ScienceProductionRate(),
            PowerShortageContingencyPolicy() # <-- REGISTER
        ]
    # ... (rest of the class) ...
```

With these two changes, the new policy is fully integrated and will be executed on every simulation step.