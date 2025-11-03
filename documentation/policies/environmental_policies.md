<!-- filepath: /Users/alexwright/Projects/Proxima/documentation/environmental_policies.md -->
# Environmental Policies

## Overview

Environmental policies in the Proxima simulation are designed to enforce adaptive behaviors based on environmental conditions, such as dust coverage on the lunar surface. These policies monitor key metrics from the `EvaluationEngine` and apply corrective actions (e.g., throttling sector activities) to maintain system stability and meet long-term goals.

The primary environmental policy is the **Dust Coverage Throttle Policy**, which dynamically adjusts operational tempo in response to increasing dust levels. This prevents excessive environmental degradation while allowing necessary activities to continue.

## Dust Coverage Throttle Policy

### Purpose

The Dust Coverage Throttle Policy (`PLCY-DUST-THROTTLE`) monitors the industrial dust coverage metric (`IND-DUST-COV`) and applies proportional throttling to affected sectors (e.g., science and manufacturing). Throttling reduces activity levels to mitigate further dust accumulation, ensuring the simulation can achieve dust-related goals without catastrophic environmental impact.

### Key Parameters

- **Metric ID**: `IND-DUST-COV` (Industrial Dust Coverage)
- **Affected Sectors**: Configurable list (default: `["science", "manufacturing"]`)
- **Throttle Factor** ($\theta_{\text{max}}$): Maximum throttle applied when dust levels are at their worst (default: 0.8, meaning 80% reduction in activity)
- **Throttle Start Ratio** ($r_{\text{start}}$): Ratio of the target dust level where throttling begins (default: 0.7, i.e., 70% of target)

### Operational Logic

The policy operates in a proactive manner:

1. **Monitor Dust Levels**: Retrieve current dust coverage ($D_{\text{current}}$) from the `EvaluationResult`.
2. **Calculate Throttling**: Determine the throttle factor based on dust levels relative to the target.
3. **Apply Throttling**: Set the throttle factor on affected sectors to reduce their operational tempo.

### Equations

#### Throttle Start Level
The level at which throttling begins is calculated as:

```math
D_{\text{start}} = D_{\text{target}} \times r_{\text{start}}
```

Where:
- $D_{\text{target}}$: The target dust coverage from the goal definition.
- $r_{\text{start}}$: The throttle start ratio (default: 0.7).

#### Throttle Factor Calculation
The throttle factor ($\theta$) is computed linearly between $D_{\text{start}}$ and $D_{\text{target}}$:

```math
\theta = 
\begin{cases} 
0 & \text{if } D_{\text{current}} \leq D_{\text{start}} \\
\min\left(1.0, \frac{D_{\text{current}} - D_{\text{start}}}{D_{\text{target}} - D_{\text{start}}}\right) \times \theta_{\text{max}} & \text{if } D_{\text{start}} < D_{\text{current}} < D_{\text{target}} \\
\theta_{\text{max}} & \text{if } D_{\text{current}} \geq D_{\text{target}}
\end{cases}
```

Where:
- $D_{\text{current}}$: Current dust coverage value.
- $\theta_{\text{max}}$: Maximum throttle factor (default: 0.8).

#### Score Integration
The policy also considers the metric score ($S$) from the `EvaluationResult` for logging and potential future enhancements:

```math
S = f(D_{\text{current}}, D_{\text{target}})
```

Where $f$ is the scoring function defined in the `EvaluationEngine` (e.g., based on proximity to target).

### Example Scenario
Suppose the target dust coverage is 1.0, and current dust is 0.8:
- $D_{\text{start}} = 1.0 \times 0.7 = 0.7$
- Since 0.8 > 0.7, throttling applies: $\theta = \min(1.0, \frac{0.8 - 0.7}{1.0 - 0.7}) \times 0.8 = 0.267$
- Affected sectors (e.g., science) have their throttle factor set to 0.267, reducing activity by ~27%.

### Configuration
The policy can be customized via its constructor:

```python
policy = DustCoverageThrottlePolicy(
    metric_id="IND-DUST-COV",
    sectors=["science", "manufacturing"],
    throttle_factor=0.8,
    throttle_start_ratio=0.7
)
```

### Effects and Logging
Upon application, the policy returns a dictionary of effects:
- `metric_id`: The monitored metric.
- `score`: Current metric score.
- `throttle_factor`: Applied throttle value.
- `applied_to`: List of sectors affected.

Logs are generated for transparency, e.g.:

```
🌪️ DUST POLICY: dust=0.800, target=1.000, start=0.700, score=0.800, throttle=0.267
🔧 Set science throttle to 0.267
```

### Future Enhancements
- **Multi-Metric Policies**: Extend to monitor additional environmental metrics (e.g., radiation levels).
- **Adaptive Ratios**: Dynamically adjust $r_{\text{start}}$ based on simulation history.
- **Sector-Specific Throttling**: Apply different throttle factors per sector based on their environmental impact.

This policy ensures the simulation balances operational needs with environmental sustainability, preventing runaway dust accumulation while allowing progress toward goals.