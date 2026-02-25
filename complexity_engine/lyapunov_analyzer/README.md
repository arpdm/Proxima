# Lyapunov Exponent Analysis for Monte Carlo Simulations

This module provides chaos analysis capabilities for Proxima lunar simulation data using Lyapunov exponents.

## Overview

The Lyapunov exponent measures the rate of separation of infinitesimally close trajectories in phase space. It's a key metric for detecting chaos and sensitivity to initial conditions:

- **Positive λ**: Chaotic behavior - small differences grow exponentially
- **Negative λ**: Stable behavior - trajectories converge
- **λ ≈ 0**: Marginally stable behavior

## Installation

Ensure you have the required dependencies:

```bash
pip install numpy pandas matplotlib
```

## Usage

### Command Line Interface

Basic usage:
```bash
python complexity_engine/chaos_analysis/run_lyapunov_analysis.py \
    --exp exp_001 \
    --session mc_1234567890 \
    --param industrial_dust_coverage
```

Advanced usage with custom parameters:
```bash
python complexity_engine/chaos_analysis/run_lyapunov_analysis.py \
    --exp exp_001 \
    --session mc_1234567890 \
    --param science_manpower \
    --dim 4 \
    --tau 2 \
    --output ./plots/custom_analysis/
```

### Arguments

**Required:**
- `--exp`: Experiment ID (e.g., `exp_001`)
- `--session`: Monte Carlo session ID (e.g., `mc_1234567890`)
- `--param`: Parameter name to analyze from CSV time series

**Optional:**
- `--log-dir`: Base directory for log files (default: `log_files`)
- `--dim`: Embedding dimension for phase space reconstruction (default: 3)
- `--tau`: Time delay for embedding (default: 1)
- `--epsilon`: Distance threshold for nearest neighbors (auto-computed if not specified)
- `--output`: Directory to save plots (default: `analysis/<param>/plots/`)
- `--max-trajectory-runs`: Max runs to plot in trajectory visualization (default: 5)
- `--no-plots`: Skip plot generation, only compute exponents
- `--verbose`: Enable verbose logging

## Output

The analysis generates:

1. **Lyapunov Distribution Plot**: Shows λ values across all runs with histogram
2. **Time Series Trajectories**: Visualizes the actual time series for selected runs
3. **Console Summary**: Statistics including mean, std deviation, and chaos assessment

### Output Structure

```
analysis/
└── <parameter_name>/
    └── plots/
        └── <session_id>/
            ├── lyapunov_distribution_<param>.png
            └── trajectories_<param>.png
```

## Example Output

```
======================================================================
RESULTS SUMMARY
======================================================================
Valid runs: 10/10
Mean Lyapunov exponent: 0.003421
Std deviation: 0.001234
Positive exponents: 8/10
⚠️  RESULT: System shows CHAOTIC behavior (positive λ)
======================================================================
```

## Programmatic Usage

You can also use the module programmatically:

```python
from complexity_engine.chaos_analysis import (
    load_monte_carlo_session_data,
    compute_lyapunov_for_session,
    plot_lyapunov_distribution
)

# Load data
run_data = load_monte_carlo_session_data(
    log_base_dir='log_files',
    experiment_id='exp_001',
    session_id='mc_1234567890',
    parameter='industrial_dust_coverage'
)

# Compute Lyapunov exponents
lyapunov_exponents = compute_lyapunov_for_session(
    run_data=run_data,
    parameter='industrial_dust_coverage',
    embedding_dim=3,
    tau=1
)

# Generate plots
plot_lyapunov_distribution(
    lyapunov_exponents=lyapunov_exponents,
    parameter='industrial_dust_coverage',
    session_id='mc_1234567890',
    output_path='analysis/lyapunov_plot.png'
)
```

## Algorithm Details

The implementation uses the method of Rosenstein et al. for Lyapunov exponent estimation:

1. **Time-Delay Embedding**: Reconstruct phase space from scalar time series
2. **Nearest Neighbor Search**: Find nearby trajectories in phase space
3. **Divergence Tracking**: Monitor separation of trajectory pairs over time
4. **Linear Regression**: Estimate λ from log-divergence slope

### Parameters

- **Embedding dimension (dim)**: Higher values capture more system complexity but require more data. Typical range: 2-5
- **Time delay (tau)**: Should correspond to approximately 1/4 of the characteristic oscillation period
- **Epsilon**: Distance threshold for considering trajectories as "nearby". Auto-computed as mean distance / 10 if not specified

## Interpreting Results

### Positive Lyapunov Exponent
- System is sensitive to initial conditions
- Small perturbations grow exponentially
- Long-term prediction becomes impossible
- Indicates complex, chaotic dynamics

### Negative Lyapunov Exponent
- System is stable and predictable
- Trajectories converge
- Initial conditions don't significantly affect outcome
- Indicates deterministic, non-chaotic behavior

### Near-Zero Lyapunov Exponent
- Marginally stable behavior
- May indicate transition between regimes
- Requires careful interpretation

## Troubleshooting

**"No valid data loaded"**: Check that CSV files exist in the Monte Carlo session folder and contain the specified parameter column.

**"Insufficient data points"**: Increase the number of steps per run in Monte Carlo simulations. Minimum recommended: `embedding_dim * tau + 20` steps.

**NaN values in results**: Some runs may not have enough data or suitable dynamics for Lyapunov calculation. This is normal - focus on runs with valid results.

## References

- Rosenstein, M.T., Collins, J.J., & De Luca, C.J. (1993). "A practical method for calculating largest Lyapunov exponents from small data sets." Physica D, 65(1-2), 117-134.
- Takens, F. (1981). "Detecting strange attractors in turbulence." Lecture Notes in Mathematics, 898, 366-381.
