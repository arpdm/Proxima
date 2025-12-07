# 📜 Proxima Policy Specification: Science Growth Doubling Policy

## 1. Overview

**Policy Goal:**  
Double the total **science production rate** every 6 months, accounting for logistical lead time in rover manufacturing and deployment.

This policy defines the algorithmic mechanism by which the system requests additional **Science Rovers** to maintain exponential growth in science output while respecting the one-month **build + shipping delay**.

---

## 2. Core Formulation

Let:

- $S(t)$ = total science production rate (units / month)  
- $S_0$ = initial science production rate at $t = 0$  
- $R(t)$ = number of operational science rovers at time $t$  
- $p_{\text{eff}}$ = effective productivity per rover (units / month / rover)  
- $L$ = lead time for rover deployment (months)  
- $H$ = planning horizon (months)  
- $\beta$ = safety margin fraction ($0 \leq \beta \leq 0.3$)

---

### 2.1 Exponential Growth Target

The policy enforces a **doubling every 6 months**:

```math
S_{\text{target}}(t) = S_0 \cdot 2^{\,t / 6}
```

For planning ahead by the lead time $H=L$:

```math
S_{\text{target}}(t+H) = S_0 \cdot 2^{\,(t + H)/6}
```

---

### 2.2 Required Rover Count

To meet the target rate, compute the required number of rovers at the horizon:

```math
R_{\text{req}}(t) = 
\left\lceil
\frac{S_{\text{target}}(t+H)}{p_{\text{eff}}}
\right\rceil
```

where

```math
p_{\text{eff}} = p \times a \times u
```

with:
- $p$ = nominal productivity per rover,  
- $a$ = availability factor (reliability),  
- $u$ = utilization factor (power / crew / comms limitations).

---

### 2.3 Forecasted Active Rovers

Estimate how many rovers will be operational when the new batch arrives:

```math
R_{\text{fore}}(t) =
R_{\text{active}}(t)
- \text{Losses}(t \!\to\! t+H)
+ \sum_{i:\,m_i \le t+H} q_i
```

where each $(m_i, q_i)$ is a **pipeline order**—a batch of $q_i$ rovers scheduled to arrive at month $m_i$.

---

### 2.4 Ordering Rule

The number of rovers to order at month $t$ is:

```math
q(t) =
\max\!\Big(
0,\;
\big\lceil(1+\beta)R_{\text{req}}(t)\big\rceil
- R_{\text{fore}}(t)
\Big)
```

Each order is placed immediately and added to the logistics pipeline with expected arrival time $t + L$.

---

## 3. Pipeline Orders

A **pipeline order** represents any rover batch currently under construction, en route, or pending deployment.

```math
\text{pipeline\_arrivals}
= \{ (m_i, q_i)\ |\ m_i > t,\, q_i > 0 \}
```

The controller consults this list each time step to avoid over-ordering and to forecast future fleet strength.

When the simulation time $t'$ reaches $m_i$, the corresponding batch $q_i$ is activated:

```math
R_{\text{active}}(t') \;{+}{=}\; q_i
```

and the entry is removed from the pipeline list.

---

## 4. Receding-Horizon Control

At every time step:

1. **Look ahead** by $H=L$.  
2. **Compute** the future target $S_{\text{target}}(t+H)$.  
3. **Determine** required rovers $R_{\text{req}}(t)$.  
4. **Forecast** expected rovers $R_{\text{fore}}(t)$.  
5. **Order** $q(t)$ rovers to fill the gap.  
6. **Advance** one month and repeat.

This creates a self-correcting loop (similar to Model Predictive Control) that adapts to failures, delays, or productivity changes.

### 4.1 System Model

Let the system evolve as:

```math
x_{t+1} = f(x_t, u_t)
```

where:
- $x_t$: system state at time $t$ (e.g., active rovers, science rate, resources)
- $u_t$: control action (e.g., new rover orders)
- $f(\cdot)$: transition function (simulated system or empirical model)

### 4.2 Optimization at Each Time Step

At time $t$, solve:

```math
\begin{align}
\min_{u} \quad & J_t = \sum_{k=0}^{H-1} \left[ (x_{t+k|t} - x_{t+k}^*)^T Q (x_{t+k|t} - x_{t+k}^*) + u_{t+k|t}^T R u_{t+k|t} \right] \\
\text{s.t.} \quad & x_{t+k+1|t} = f(x_{t+k|t}, u_{t+k|t}), \\
& x_{t+k|t} \in \mathcal{X}, \quad u_{t+k|t} \in \mathcal{U}
\end{align}
```

Where:
- $H$: horizon length (in months)
- $x^*$: desired trajectory or target (e.g., doubling curve)
- $Q, R$: weighting matrices penalizing deviation and control effort
- $\mathcal{X}, \mathcal{U}$: constraints (resource, logistics, production capacity)

### 4.3 Control Application

After solving:

1. Apply only the first control action $u_{t|t}^*$.
2. At $t+1$, update $x_{t+1}$, shift the horizon, and repeat.

This receding-horizon approach provides robust adaptive control that continuously re-optimizes based on the current state, handling uncertainties such as rover failures, resource shortages, and production delays.

---

## 5. Example Scenario

| Parameter | Value |
|------------|-------|
| $S_0$ | 100 units / month |
| $p_{\text{eff}}$ | 10 units / rover / month |
| $L=H$ | 1 month |
| $\beta$ | 0.1 |
| $R_{\text{active}}(0)$ | 10 rovers |

At month 5:

```math
\begin{align}
S_{\text{target}}(6) &= 100 \times 2^{6/6} = 200 \\
R_{\text{req}}(5) &= \lceil 200 / 10 \rceil = 20 \\
R_{\text{fore}}(5) &= 10 - 1 + 5 = 14 \quad (\text{one failure, five in pipeline}) \\
q(5) &= (1.1 \times 20) - 14 = 8
\end{align}
```

→ **Order 8 rovers** for delivery at month 6.

---

## 6. Pseudocode Implementation

```python
def order_rovers(t, S0, peff, L=1, beta=0.1,
                 R_active=0, pipeline_arrivals=[], expected_losses=0):
    H = L
    S_target = S0 * (2 ** ((t + H) / 6.0))
    R_req = math.ceil(S_target / peff)

    arrivals_by_H = sum(q for (m, q) in pipeline_arrivals if m <= t + H)
    R_fore = R_active - expected_losses + arrivals_by_H

    q = max(0, math.ceil((1 + beta) * R_req) - R_fore)
    return q
```

---

## 7. Future Enhancements

- **Dynamic Productivity Adjustment**: Update $p_{\text{eff}}$ based on real-time rover performance.
- **Multi-Resource Constraints**: Factor in power, crew, and material availability.
- **Failure Prediction**: Use historical failure rates to improve loss forecasting.
- **Variable Lead Times**: Account for different manufacturing speeds or supply chain disruptions.
- **Full MPC Implementation**: Implement the complete optimization formulation with $Q$ and $R$ matrices for more sophisticated control.

This policy ensures exponential growth in science output while maintaining a robust, adaptive planning mechanism.

## 8. ML/DL Additions

1. Reinforcement Learning (RL) for Adaptive Control
Use Case: Replace the simple receding-horizon controller with an RL agent that learns optimal rover ordering policies.

```python
from stable_baselines3 import PPO, SAC
import gymnasium as gym
```

2. Time Series Forecasting for Demand Prediction
Use Case: Predict future science production rates and power demands more accurately.

3. Anomaly Detection for Rover Failures
Use Case: Predict when rovers are likely to fail based on usage patterns. (IsolationForest)

4. Multi-Armed Bandit for Task Prioritization
Use Case: If rovers can do different science tasks, use contextual bandits to learn which tasks yield most value.

5. Graph Neural Networks for Rover Coordination
Use Case: If rovers interact or share resources, use GNNs to optimize coordination.

```python
import torch
import torch.nn as nn
from torch_geometric.nn import GCNConv
```

6. Imitation Learning for Policy Initialization
Use Case: Bootstrap RL with expert demonstrations (your current heuristic policy).

```python
from imitation.algorithms import bc
```
