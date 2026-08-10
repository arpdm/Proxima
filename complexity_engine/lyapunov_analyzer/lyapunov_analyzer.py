"""
lyapunov_analyzer.py

PROXIMA LUNAR SIMULATION - LYAPUNOV EXPONENT ANALYSIS

PURPOSE:
========
Calculates Lyapunov exponents for time series data from Monte Carlo simulations
to detect chaos and sensitivity to initial conditions.

FEATURES:
=========
- Lyapunov exponent calculation for arbitrary time series
- Monte Carlo session data loading and processing
- Configurable parameter selection
- Data-independent design
- Visualization of Lyapunov exponents across runs
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class LyapunovAnalyzer:
    """
    Analyzes time series data for chaos using Lyapunov exponents.
    
    The Lyapunov exponent measures the rate of separation of infinitesimally
    close trajectories. Positive values indicate chaos/sensitivity to initial
    conditions, negative values indicate stable/predictable behavior.
    """

    def __init__(self, time_series: np.ndarray, dt: float = 1.0):
        """
        Initialize analyzer with time series data.
        
        Args:
            time_series: 1D array of time series values
            dt: Time step between measurements (default: 1.0)
        """
        self.time_series = np.array(time_series)
        self.dt = dt
        self.n = len(time_series)

    def compute_lyapunov_exponent(
        self,
        embedding_dim: int = 3,
        tau: int = 1,
        epsilon: Optional[float] = None,
        min_evolution_steps: int = 10
    ) -> float:
        """
        Compute the largest Lyapunov exponent using the method of Rosenstein et al.
        
        Args:
            embedding_dim: Embedding dimension for phase space reconstruction
            tau: Time delay for embedding
            epsilon: Maximum distance for nearest neighbors (auto if None)
            min_evolution_steps: Minimum steps to track divergence
            
        Returns:
            Largest Lyapunov exponent estimate
        """
        # Perform time delay embedding
        embedded = self._time_delay_embedding(embedding_dim, tau)
        
        if embedded.shape[0] < 2:
            logger.warning("Not enough data points for Lyapunov calculation")
            return np.nan
        
        logger.debug(f"Embedded space: {embedded.shape}, data range: [{np.min(embedded):.6f}, {np.max(embedded):.6f}]")
        
        # Find nearest neighbors
        neighbors = self._find_nearest_neighbors(embedded, epsilon)
        
        # Track divergence over time
        divergence = self._track_divergence(embedded, neighbors, min_evolution_steps)
        
        if len(divergence) == 0:
            logger.warning("No valid divergence data")
            return np.nan
        
        # Calculate Lyapunov exponent from divergence slope
        lyapunov = self._estimate_lyapunov(divergence)
        
        return lyapunov

    def _time_delay_embedding(self, dim: int, tau: int) -> np.ndarray:
        """
        Create time-delay embedding for phase space reconstruction.
        
        Args:
            dim: Embedding dimension
            tau: Time delay
            
        Returns:
            Embedded vectors as (n_vectors, dim) array
        """
        n_vectors = self.n - (dim - 1) * tau
        
        if n_vectors <= 0:
            return np.array([])
        
        embedded = np.zeros((n_vectors, dim))
        for i in range(dim):
            embedded[:, i] = self.time_series[i * tau : i * tau + n_vectors]
        
        return embedded

    def _find_nearest_neighbors(
        self, 
        embedded: np.ndarray, 
        epsilon: Optional[float] = None
    ) -> List[Tuple[int, int, float]]:
        """
        Find nearest neighbors in phase space.
        
        Args:
            embedded: Embedded phase space vectors
            epsilon: Maximum distance threshold (auto-computed if None)
            
        Returns:
            List of (index, neighbor_index, distance) tuples
        """
        n_points = embedded.shape[0]
        neighbors = []
        
        # Auto-compute epsilon as mean pairwise distance / 5 (less strict)
        if epsilon is None:
            sample_size = min(100, n_points)
            indices = np.random.choice(n_points, sample_size, replace=False)
            distances = []
            for i in indices:
                for j in indices:
                    if i != j:
                        dist = np.linalg.norm(embedded[i] - embedded[j])
                        distances.append(dist)
            if distances:
                mean_dist = np.mean(distances)
                epsilon = max(mean_dist / 5.0, np.std(embedded) * 0.5)  # At least std * 0.5
            else:
                epsilon = 1.0
        
        logger.debug(f"Epsilon: {epsilon:.6f}, embedded std: {np.std(embedded):.6f}")
        
        # Find nearest neighbors within epsilon
        for i in range(n_points):
            for j in range(i + 1, n_points):
                # Avoid very close temporal neighbors
                if abs(i - j) < 2:
                    continue
                
                dist = np.linalg.norm(embedded[i] - embedded[j])
                if dist < epsilon and dist > 0:
                    neighbors.append((i, j, dist))
                    
        logger.debug(f"Found {len(neighbors)} neighbor pairs out of {n_points*(n_points-1)//2} possible with epsilon={epsilon:.6f}")
        
        return neighbors

    def _track_divergence(
        self,
        embedded: np.ndarray,
        neighbors: List[Tuple[int, int, float]],
        min_steps: int
    ) -> List[Tuple[int, float]]:
        """
        Track divergence of nearby trajectories over time.
        
        Args:
            embedded: Phase space vectors
            neighbors: List of neighbor pairs
            min_steps: Minimum evolution steps
            
        Returns:
            List of (time_step, log_divergence) tuples
        """
        n_points = embedded.shape[0]
        divergence = []
        
        if not neighbors:
            logger.warning("No neighbor pairs found for divergence tracking")
            return divergence
        
        for i, j, initial_dist in neighbors:
            max_steps = min(min_steps, n_points - max(i, j) - 1)
            
            if max_steps < 1:
                continue
            
            for k in range(1, max_steps + 1):
                if i + k >= n_points or j + k >= n_points:
                    break
                
                current_dist = np.linalg.norm(embedded[i + k] - embedded[j + k])
                
                if current_dist > 0:
                    log_div = np.log(current_dist)
                    divergence.append((k, log_div))
        
        logger.debug(f"Tracked {len(divergence)} divergence points from {len(neighbors)} neighbors")
        return divergence

    def _estimate_lyapunov(self, divergence: List[Tuple[int, float]]) -> float:
        """
        Estimate Lyapunov exponent from divergence data.
        
        Args:
            divergence: List of (time_step, log_divergence) pairs
            
        Returns:
            Lyapunov exponent estimate
        """
        if not divergence:
            return np.nan
        
        # Convert to arrays and average log divergence at each time step
        times = np.array([d[0] for d in divergence])
        log_divs = np.array([d[1] for d in divergence])
        
        # Group by time step and compute mean
        unique_times = np.unique(times)
        mean_log_divs = []
        
        for t in unique_times:
            mask = times == t
            mean_log_divs.append(np.mean(log_divs[mask]))
        
        # Fit linear regression to get slope
        if len(unique_times) < 2:
            return np.nan
        
        slope, _ = np.polyfit(unique_times * self.dt, mean_log_divs, 1)
        
        return slope


def load_monte_carlo_session_data(
    log_base_dir: str,
    experiment_id: str,
    session_id: str,
    parameter: str
) -> Dict[int, pd.DataFrame]:
    """
    Load time series data for all runs in a Monte Carlo session.
    
    Loads CSV files from the session directory and extracts data by monte_carlo_run_index.
    
    Args:
        log_base_dir: Base directory for log files (e.g., "log_files")
        experiment_id: Experiment identifier (e.g., "exp_001")
        session_id: Monte Carlo session identifier (e.g., "mc_1234567890")
        parameter: Parameter name to extract from time series
        
    Returns:
        Dictionary mapping run_index -> DataFrame with time series data
    """
    session_path = Path(log_base_dir) / "monte_carlo" / experiment_id / session_id
    
    if not session_path.exists():
        raise FileNotFoundError(f"Session directory not found: {session_path}")
    
    run_data = {}
    
    # Load CSV files from session directory
    csv_files = sorted(session_path.glob("*.csv"))
    
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in session directory: {session_path}")
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            
            if parameter not in df.columns:
                logger.warning(f"Parameter '{parameter}' not found in {csv_file.name}")
                continue
            
            # Extract data by monte_carlo_run_index
            if 'monte_carlo_run_index' in df.columns:
                run_indices = df['monte_carlo_run_index'].unique()
                for run_index in run_indices:
                    run_index = int(run_index)
                    run_df = df[df['monte_carlo_run_index'] == run_index]
                    run_data[run_index] = run_df
            else:
                logger.warning(f"No 'monte_carlo_run_index' column in {csv_file.name}, skipping")
                continue
                
        except Exception as e:
            logger.error(f"Error loading {csv_file}: {e}")
            continue
    
    if not run_data:
        raise ValueError(f"No valid data loaded for parameter '{parameter}' from session {session_id}")
    
    logger.info(f"Loaded {len(run_data)} runs for parameter '{parameter}'")
    
    return run_data


def compute_lyapunov_for_session(
    run_data: Dict[int, pd.DataFrame],
    parameter: str,
    embedding_dim: int = 3,
    tau: int = 1,
    epsilon: Optional[float] = None
) -> Dict[int, float]:
    """
    Compute Lyapunov exponents for all runs in a session.
    
    Args:
        run_data: Dictionary mapping run_index -> DataFrame
        parameter: Parameter name to analyze
        embedding_dim: Embedding dimension for phase space
        tau: Time delay for embedding
        epsilon: Distance threshold for neighbors
        
    Returns:
        Dictionary mapping run_index -> Lyapunov exponent
    """
    lyapunov_exponents = {}
    
    for run_index, df in run_data.items():
        try:
            # Extract time series and convert to numeric
            time_series = pd.to_numeric(df[parameter], errors='coerce').values
            
            # Check for NaN values
            valid_mask = ~np.isnan(time_series)
            if not valid_mask.any():
                logger.warning(f"Run {run_index}: all NaN values in parameter")
                lyapunov_exponents[run_index] = np.nan
                continue
            
            time_series = time_series[valid_mask]
            
            # Check if there's actual variation in the data
            data_std = np.std(time_series)
            if data_std < 1e-10:
                logger.warning(f"Run {run_index}: insufficient variation (std={data_std:.2e})")
                lyapunov_exponents[run_index] = np.nan
                continue
            
            # Skip if not enough data
            if len(time_series) < embedding_dim * tau + 10:
                logger.warning(f"Run {run_index}: insufficient data points ({len(time_series)})")
                lyapunov_exponents[run_index] = np.nan
                continue
            
            analyzer = LyapunovAnalyzer(time_series)
            lyapunov = analyzer.compute_lyapunov_exponent(
                embedding_dim=embedding_dim,
                tau=tau,
                epsilon=epsilon
            )
            
            lyapunov_exponents[run_index] = lyapunov
            logger.info(f"Run {run_index}: λ = {lyapunov:.6f}")
            
        except Exception as e:
            logger.error(f"Run {run_index} error: {e}")
            lyapunov_exponents[run_index] = np.nan
    
    return lyapunov_exponents


def plot_lyapunov_distribution(
    lyapunov_exponents: Dict[int, float],
    parameter: str,
    session_id: str,
    output_path: Optional[str] = None
) -> None:
    """
    Plot distribution of Lyapunov exponents across Monte Carlo runs.
    
    Args:
        lyapunov_exponents: Dictionary mapping run_index -> Lyapunov exponent
        parameter: Parameter name being analyzed
        session_id: Monte Carlo session identifier
        output_path: Path to save plot (displays if None)
    """
    # Filter out NaN values
    valid_exponents = {k: v for k, v in lyapunov_exponents.items() if not np.isnan(v)}
    
    if not valid_exponents:
        logger.error("No valid Lyapunov exponents to plot")
        return
    
    runs = list(valid_exponents.keys())
    exponents = list(valid_exponents.values())
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    
    # Plot 1: Lyapunov exponent by run
    ax1.plot(runs, exponents, 'o-', markersize=6, linewidth=1.5, alpha=0.7)
    ax1.axhline(y=0, color='r', linestyle='--', linewidth=1, alpha=0.5, label='λ = 0')
    ax1.set_xlabel('Run Index', fontsize=11)
    ax1.set_ylabel('Lyapunov Exponent (λ)', fontsize=11)
    ax1.set_title(f'Lyapunov Exponents: {parameter}', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # Plot 2: Histogram of exponents
    ax2.hist(exponents, bins=min(20, len(exponents)), alpha=0.7, color='steelblue', edgecolor='black')
    ax2.axvline(x=0, color='r', linestyle='--', linewidth=1.5, alpha=0.5, label='λ = 0')
    ax2.set_xlabel('Lyapunov Exponent (λ)', fontsize=11)
    ax2.set_ylabel('Frequency', fontsize=11)
    ax2.set_title('Distribution of Lyapunov Exponents', fontsize=12, fontweight='bold')
    ax2.grid(True, alpha=0.3, axis='y')
    ax2.legend()
    
    # Add statistics
    mean_lambda = np.mean(exponents)
    std_lambda = np.std(exponents)
    positive_count = sum(1 for e in exponents if e > 0)
    
    stats_text = f'Mean λ: {mean_lambda:.4f}\nStd λ: {std_lambda:.4f}\nPositive: {positive_count}/{len(exponents)}'
    ax2.text(0.95, 0.95, stats_text, transform=ax2.transAxes,
             verticalalignment='top', horizontalalignment='right',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
             fontsize=9)
    
    plt.suptitle(f'Monte Carlo Session: {session_id}', fontsize=13, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        logger.info(f"Plot saved to: {output_path}")
    else:
        plt.show()
    
    plt.close()


def analyze_time_series_trajectory(
    run_data: Dict[int, pd.DataFrame],
    parameter: str,
    max_runs: int = 5,
    output_path: Optional[str] = None
) -> None:
    """
    Plot time series trajectories for selected runs.
    
    Args:
        run_data: Dictionary mapping run_index -> DataFrame
        parameter: Parameter name to plot
        max_runs: Maximum number of runs to plot
        output_path: Path to save plot (displays if None)
    """
    selected_runs = sorted(run_data.keys())[:max_runs]
    
    plt.figure(figsize=(12, 6))
    
    for run_index in selected_runs:
        df = run_data[run_index]
        plt.plot(df['step'], df[parameter], alpha=0.7, linewidth=1.5, label=f'Run {run_index}')
    
    plt.xlabel('Simulation Step', fontsize=11)
    plt.ylabel(parameter, fontsize=11)
    plt.title(f'Time Series Trajectories: {parameter}', fontsize=12, fontweight='bold')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        logger.info(f"Trajectory plot saved to: {output_path}")
    else:
        plt.show()
    
    plt.close()
