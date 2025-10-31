
# Dust Coverage Index - Throttling

## Problem Background

**[TBD]**

## Functional Defintion

This policy dynamically throttles the operational capacity of designated sectors based on the current industrial dust coverage metric (`IND-DUST-COV`). The goal is to proactively reduce dust-generating activities as coverage approaches its target limit, preventing excessive environmental impact.

## Case Studies

**[TBD]**

## Equation


First, the dust level at which throttling begins is determined:

```math
D_{\text{start}} = D_{\text{target}} \times R_{\text{start}}
```

The current throttle factor, $\text{current}$, is then calculated using a piecewise function:

```math
T_{\text{current}} = \begin{cases} 0 & \text{if } D_{\text{current}} \le D_{\text{start}} \\ \min\left(1, \frac{D_{\text{current}} - D_{\text{start}}}{D_{\text{target}} - D_{\text{start}}}\right) \times F_{\text{throttle}} & \text{if } D_{\text{current}} > D_{\text{start}} \end{cases}
```

**Explanation:**

The throttling factor, $T_{\text{current}}$, is calculated based on the following variables:

- $T_{\text{current}}$: The calculated throttle factor to be applied to sectors.
- $D_{\text{current}}$: The current measured dust coverage.
- $D_{\text{target}}$: The performance goal's target value for dust coverage.
- $D_{\text{start}}$: The calculated dust level at which throttling begins.
- $R_{\text{start}}$: A configurable ratio (e.g., 0.7) that defines the throttling start point relative to the target.
- $F_{\text{throttle}}$: The maximum throttle factor to be applied (e.g., 0.8 for 80% throttling).


## Algorithm

This calculated throttle factor is then applied to the configured sectors (e.g., `science`, `manufacturing`) to reduce their operational output for the simulation step.

## Side Effects

One of the most notable negative side effects of this policy is slowed down functionality of agents where it affects the growth and advancement rate.

On the other hand, this policy allows environmental dust to settle before reusming operations to avoid dust poliution. This would be specifically important with humans on board as well as for visibility of other autmated machines where rely on vision through cameras for their operations.
