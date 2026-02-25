#!/usr/bin/env python3
"""
run_lyapunov_analysis.py

PROXIMA LUNAR SIMULATION - LYAPUNOV ANALYSIS CLI

PURPOSE:
========
Command-line interface for running Lyapunov exponent analysis on Monte Carlo
simulation data. Analyzes sensitivity to initial conditions and chaos.

USAGE:
======
python run_lyapunov_analysis.py --exp exp_001 --session mc_1234567890 --param industrial_dust_coverage

"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional
import pandas as pd
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from complexity_engine.lyapunov_analyzer.lyapunov_analyzer import (
    load_monte_carlo_session_data,
    compute_lyapunov_for_session,
    plot_lyapunov_distribution,
    analyze_time_series_trajectory
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Compute Lyapunov exponents for Monte Carlo simulation data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze industrial dust coverage
  python run_lyapunov_analysis.py --exp exp_001 --session mc_1234567890 --param industrial_dust_coverage
  
  # Analyze with custom embedding parameters
  python run_lyapunov_analysis.py --exp exp_001 --session mc_1234567890 --param science_manpower --dim 4 --tau 2
  
  # Save plots to custom location
  python run_lyapunov_analysis.py --exp exp_001 --session mc_1234567890 --param temperature --output ./plots/
        """
    )
    
    parser.add_argument(
        '--exp', '--experiment',
        dest='experiment_id',
        required=True,
        help='Experiment ID (e.g., exp_001)'
    )
    
    parser.add_argument(
        '--session',
        required=True,
        help='Monte Carlo session ID (e.g., mc_1234567890)'
    )
    
    parser.add_argument(
        '--param', '--parameter',
        dest='parameter',
        required=True,
        help='Parameter name to analyze from time series data'
    )
    
    parser.add_argument(
        '--log-dir',
        default='log_files',
        help='Base directory for log files (default: log_files)'
    )
    
    parser.add_argument(
        '--dim', '--embedding-dim',
        dest='embedding_dim',
        type=int,
        default=3,
        help='Embedding dimension for phase space reconstruction (default: 3)'
    )
    
    parser.add_argument(
        '--tau', '--time-delay',
        dest='tau',
        type=int,
        default=1,
        help='Time delay for embedding (default: 1)'
    )
    
    parser.add_argument(
        '--epsilon',
        type=float,
        default=None,
        help='Distance threshold for nearest neighbors (auto-computed if not specified)'
    )
    
    parser.add_argument(
        '--output', '--output-dir',
        dest='output_dir',
        default=None,
        help='Directory to save output plots (default: analysis/<param>/plots/)'
    )
    
    parser.add_argument(
        '--max-trajectory-runs',
        type=int,
        default=5,
        help='Maximum runs to plot in trajectory visualization (default: 5)'
    )
    
    parser.add_argument(
        '--no-plots',
        action='store_true',
        help='Skip plot generation, only compute Lyapunov exponents'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser.parse_args()


def setup_output_directory(
    output_dir: Optional[str],
    experiment_id: str,
    session_id: str,
    parameter: str
) -> Path:
    """
    Setup output directory for plots.
    
    Args:
        output_dir: User-specified output directory (or None)
        experiment_id: Experiment identifier
        session_id: Session identifier
        parameter: Parameter name
        
    Returns:
        Path to output directory
    """
    if output_dir:
        output_path = Path(output_dir)
    else:
        # Default: analysis/<param>/plots/<session_id>/
        output_path = Path('analysis') / parameter.replace(' ', '_') / 'plots' / session_id
    
    output_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_path}")
    
    return output_path


def main():
    """Main execution function."""
    args = parse_arguments()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("=" * 70)
    logger.info("PROXIMA LYAPUNOV EXPONENT ANALYSIS")
    logger.info("=" * 70)
    logger.info(f"Experiment ID: {args.experiment_id}")
    logger.info(f"Session ID: {args.session}")
    logger.info(f"Parameter: {args.parameter}")
    logger.info(f"Embedding dimension: {args.embedding_dim}")
    logger.info(f"Time delay (tau): {args.tau}")
    logger.info(f"Epsilon: {'auto' if args.epsilon is None else args.epsilon}")
    logger.info("=" * 70)
    
    try:
        # Load Monte Carlo session data
        logger.info("Loading Monte Carlo session data...")
        run_data = load_monte_carlo_session_data(
            log_base_dir=args.log_dir,
            experiment_id=args.experiment_id,
            session_id=args.session,
            parameter=args.parameter
        )
        
        # Compute Lyapunov exponents
        logger.info("Computing Lyapunov exponents...")
        lyapunov_exponents = compute_lyapunov_for_session(
            run_data=run_data,
            parameter=args.parameter,
            embedding_dim=args.embedding_dim,
            tau=args.tau,
            epsilon=args.epsilon
        )
        
        # Display results summary
        logger.info("=" * 70)
        logger.info("RESULTS SUMMARY")
        logger.info("=" * 70)
        
        valid_exponents = [v for v in lyapunov_exponents.values() if not pd.isna(v)]
        
        if valid_exponents:
            import numpy as np
            mean_lambda = np.mean(valid_exponents)
            std_lambda = np.std(valid_exponents)
            positive_count = sum(1 for e in valid_exponents if e > 0)
            
            logger.info(f"Valid runs: {len(valid_exponents)}/{len(lyapunov_exponents)}")
            logger.info(f"Mean Lyapunov exponent: {mean_lambda:.6f}")
            logger.info(f"Std deviation: {std_lambda:.6f}")
            logger.info(f"Positive exponents: {positive_count}/{len(valid_exponents)}")
            
            if mean_lambda > 0:
                logger.info("⚠️  RESULT: System shows CHAOTIC behavior (positive λ)")
            else:
                logger.info("✅ RESULT: System shows STABLE behavior (negative λ)")
        else:
            logger.error("No valid Lyapunov exponents computed")
            return 1
        
        # Generate plots
        if not args.no_plots:
            output_path = setup_output_directory(
                args.output_dir,
                args.experiment_id,
                args.session,
                args.parameter
            )
            
            logger.info("Generating plots...")
            
            # Lyapunov distribution plot
            dist_plot_path = output_path / f"lyapunov_distribution_{args.parameter}.png"
            plot_lyapunov_distribution(
                lyapunov_exponents=lyapunov_exponents,
                parameter=args.parameter,
                session_id=args.session,
                output_path=str(dist_plot_path)
            )
            
            # Time series trajectory plot
            traj_plot_path = output_path / f"trajectories_{args.parameter}.png"
            analyze_time_series_trajectory(
                run_data=run_data,
                parameter=args.parameter,
                max_runs=args.max_trajectory_runs,
                output_path=str(traj_plot_path)
            )
            
            logger.info(f"✅ Plots saved to: {output_path}")
        
        logger.info("=" * 70)
        logger.info("Analysis complete!")
        logger.info("=" * 70)
        
        return 0
        
    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Value error: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    import pandas as pd
    import numpy as np
    sys.exit(main())
