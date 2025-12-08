"""
Time Series Analyzer for Proxima Simulation Data

This script provides configurable time series analysis and visualization
for Proxima simulation outputs. It supports single-run analysis with
extensibility for future stochastic runs.

Features:
- Configurable plotting options
- Multiple visualization types
- Statistical analysis
- Trend detection
- Rolling statistics
- Comparative analysis (when multiple runs available)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import yaml
from typing import Dict, List, Optional, Union, Tuple
import warnings
from datetime import datetime
import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import argparse

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# Set up plotting style
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")

# Set Plotly template
pio.templates.default = "plotly_white"

class TimeSeriesAnalyzer:
    """
    Configurable time series analyzer for Proxima simulation data.
    
    Supports:
    - Single and multi-run analysis
    - Various plot types
    - Statistical summaries
    - Trend analysis
    - Rolling statistics
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize analyzer with configuration.
        
        Args:
            config: Configuration dictionary or path to YAML config file
        """
        self.config = self._load_config(config)
        self.data = {}
        self.analysis_results = {}
        
    def _load_config(self, config: Union[Dict, str, None]) -> Dict:
        """Load configuration from dict, YAML file, or use defaults."""
        
        if isinstance(config, str):
            with open(config, 'r') as f:
                user_config = yaml.safe_load(f)
        elif isinstance(config, dict):
            user_config = None

        return user_config
    
    def load_data(self, file_paths: Union[str, List[str], Path] = None) -> Dict[str, pd.DataFrame]:
        """
        Load CSV data into pandas DataFrames.
        
        Args:
            file_paths: Path(s) to CSV files. If None, uses config paths.
            
        Returns:
            Dictionary of DataFrames keyed by filename
        """
        if file_paths is None:
            input_dir = Path(self.config['data']['input_dir'])
            file_pattern = self.config['data']['file_pattern']
            file_paths = list(input_dir.glob(file_pattern))
        
        if isinstance(file_paths, (str, Path)):
            file_paths = [file_paths]
            
        for file_path in file_paths:
            file_path = Path(file_path)
            if file_path.exists():
                df = pd.read_csv(
                    file_path,
                    index_col=self.config['data']['index_col']
                )
                
                # Ensure time column exists
                time_col = self.config['data']['time_column']
                if time_col not in df.columns:
                    print(f"Warning: Time column '{time_col}' not found in {file_path.name}")
                    continue
                    
                # Set time column as index if not already
                if df.index.name != time_col:
                    df = df.set_index(time_col)
                    
                self.data[file_path.stem] = df
                print(f"Loaded {file_path.name}: {len(df)} rows, {len(df.columns)} columns")
            else:
                print(f"File not found: {file_path}")
                
        return self.data
    
    def compute_rolling_stats(self, df: pd.DataFrame, features: List[str] = None) -> Dict[str, pd.DataFrame]:
        """
        Compute rolling statistics for specified features.
        
        Args:
            df: Input DataFrame
            features: Features to analyze. If None, uses config.
            
        Returns:
            Dictionary of rolling statistics DataFrames
        """
        if features is None:
            features = self.config['analysis']['features']
            
        window = self.config['analysis']['rolling_window']
        method = self.config['analysis']['smoothing_method']
        
        rolling_stats = {}
        
        for feature in features:
            if feature not in df.columns:
                print(f"Warning: Feature '{feature}' not found in data")
                continue
                
            series = df[feature].dropna()
            
            if method == 'rolling':
                rolling_mean = series.rolling(window=window, center=True).mean()
                rolling_std = series.rolling(window=window, center=True).std()
            elif method == 'ewm':
                rolling_mean = series.ewm(span=window).mean()
                rolling_std = series.ewm(span=window).std()
            elif method == 'savgol':
                from scipy.signal import savgol_filter
                # Savitzky-Golay filter for smoothing
                if len(series) > window:
                    rolling_mean = pd.Series(
                        savgol_filter(series.values, window, 3),
                        index=series.index
                    )
                    rolling_std = series.rolling(window=window, center=True).std()
                else:
                    rolling_mean = series.rolling(window=window, center=True).mean()
                    rolling_std = series.rolling(window=window, center=True).std()
            else:
                rolling_mean = series.rolling(window=window, center=True).mean()
                rolling_std = series.rolling(window=window, center=True).std()
                
            stats_df = pd.DataFrame({
                f'{feature}_raw': series,
                f'{feature}_mean': rolling_mean,
                f'{feature}_std': rolling_std,
                f'{feature}_upper': rolling_mean + rolling_std,
                f'{feature}_lower': rolling_mean - rolling_std
            })
            
            rolling_stats[feature] = stats_df
            
        return rolling_stats
    
    def detect_trends(self, df: pd.DataFrame, features: List[str] = None) -> Dict[str, Dict]:
        """
        Detect trends in time series using linear regression.
        
        Args:
            df: Input DataFrame
            features: Features to analyze
            
        Returns:
            Dictionary of trend analysis results
        """
        from scipy.stats import linregress
        
        if features is None:
            features = self.config['analysis']['features']
            
        trends = {}
        
        for feature in features:
            if feature not in df.columns:
                continue
                
            series = df[feature].dropna()
            x = np.arange(len(series))
            y = series.values
            
            slope, intercept, r_value, p_value, std_err = linregress(x, y)
            
            # Calculate trend line
            trend_line = slope * x + intercept
            
            trends[feature] = {
                'slope': slope,
                'intercept': intercept,
                'r_squared': r_value**2,
                'p_value': p_value,
                'trend_direction': 'increasing' if slope > 0 else 'decreasing',
                'trend_strength': abs(slope),
                'trend_line': trend_line,
                'x_values': x
            }
            
        return trends
    
    def plot_time_series_grid(self, data_dict: Dict[str, pd.DataFrame] = None, 
                            save_path: str = None) -> plt.Figure:
        """
        Create a grid of time series plots for multiple features.
        
        Args:
            data_dict: Dictionary of DataFrames (one per run)
            save_path: Path to save plot
            
        Returns:
            Matplotlib figure object
        """
        if data_dict is None:
            data_dict = self.data
            
        if not data_dict:
            raise ValueError("No data loaded. Call load_data() first.")
            
        features = self.config['analysis']['features']
        n_cols = self.config['plotting']['grid_plots']['n_cols']
        n_features = len(features)
        n_rows = (n_features + n_cols - 1) // n_cols
        
        fig, axes = plt.subplots(
            n_rows, n_cols, 
            figsize=(self.config['plotting']['figsize'][0], 
                    self.config['plotting']['figsize'][1] * n_rows / 2),
            sharex=True
        )
        
        if n_rows == 1:
            axes = axes.reshape(1, -1)
        elif n_cols == 1:
            axes = axes.reshape(-1, 1)
            
        # Flatten axes for easier iteration
        axes_flat = axes.flatten()
        
        for i, feature in enumerate(features):
            ax = axes_flat[i]
            
            for run_name, df in data_dict.items():
                if feature in df.columns:
                    series = df[feature].dropna()
                    ax.plot(series.index, series.values, 
                           label=run_name if len(data_dict) > 1 else feature,
                           linewidth=self.config['plotting']['time_series']['line_width'],
                           alpha=self.config['plotting']['time_series']['alpha'])
                    
            ax.set_title(f'{feature.replace("_", " ").title()}')
            ax.grid(True, alpha=0.3)
            
            if i % n_cols == 0:  # Leftmost column
                ax.set_ylabel('Value')
            if i >= n_features - n_cols:  # Bottom row
                ax.set_xlabel('Time (steps)')
                
        # Hide empty subplots
        for i in range(n_features, len(axes_flat)):
            axes_flat[i].set_visible(False)
            
        # Add legend if multiple runs
        if len(data_dict) > 1:
            handles, labels = axes_flat[0].get_legend_handles_labels()
            fig.legend(handles, labels, loc='upper center', 
                      bbox_to_anchor=(0.5, 0.95), ncol=min(4, len(data_dict)))
            
        plt.tight_layout()
        
        if save_path:
            self._save_plot(fig, save_path)
            
        return fig
    
    def plot_rolling_stats(self, df: pd.DataFrame, features: List[str] = None,
                          save_path: str = None) -> plt.Figure:
        """
        Plot rolling statistics with confidence bands.
        
        Args:
            df: Input DataFrame
            features: Features to plot
            save_path: Path to save plot
            
        Returns:
            Matplotlib figure object
        """
        if features is None:
            features = self.config['analysis']['features']
            
        rolling_stats = self.compute_rolling_stats(df, features)
        
        n_features = len(features)
        fig, axes = plt.subplots(n_features, 1, 
                               figsize=(self.config['plotting']['figsize'][0],
                                       self.config['plotting']['figsize'][1] * n_features / 2),
                               sharex=True)
        
        if n_features == 1:
            axes = [axes]
            
        for i, feature in enumerate(features):
            ax = axes[i]
            stats_df = rolling_stats[feature]
            
            # Plot raw data
            ax.plot(stats_df.index, stats_df[f'{feature}_raw'], 
                   alpha=0.6, color='lightgray', label='Raw Data')
            
            # Plot rolling mean
            if self.config['plotting']['rolling_stats']['show_mean']:
                ax.plot(stats_df.index, stats_df[f'{feature}_mean'], 
                       linewidth=2, label='Rolling Mean')
                
            # Plot confidence bands
            if self.config['plotting']['rolling_stats']['show_std']:
                ax.fill_between(stats_df.index, 
                               stats_df[f'{feature}_lower'], 
                               stats_df[f'{feature}_upper'],
                               alpha=0.3, label='±1 Std Dev')
                
            # Plot trend line
            if self.config['analysis']['trend_analysis'] and self.config['plotting']['rolling_stats']['show_trend']:
                trends = self.detect_trends(df, [feature])
                if feature in trends:
                    trend_data = trends[feature]
                    ax.plot(stats_df.index, trend_data['trend_line'],
                           '--', linewidth=2, color='red', label='Trend')
                    
            ax.set_title(f'{feature.replace("_", " ").title()} - Rolling Statistics')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
        plt.xlabel('Time (months)')
        plt.tight_layout()
        
        if save_path:
            self._save_plot(fig, save_path)
            
        return fig
    
    def plot_autocorrelation(self, df: pd.DataFrame, features: List[str] = None,
                       save_path: str = None) -> plt.Figure:
        """
        Plot autocorrelation function for time series using statsmodels.
        
        Args:
            df: Input DataFrame
            features: Features to analyze
            save_path: Path to save plot
            
        Returns:
            Matplotlib figure object
        """
        from statsmodels.graphics.tsaplots import plot_acf
        
        if features is None:
            features = self.config['analysis']['features']
            
        n_features = len(features)
        fig, axes = plt.subplots(n_features, 1,
                               figsize=(self.config['plotting']['figsize'][0],
                                       self.config['plotting']['figsize'][1] * n_features / 2))
        
        if n_features == 1:
            axes = [axes]
            
        lags = self.config['analysis']['autocorr_lags']
        
        for i, feature in enumerate(features):
            ax = axes[i]
            
            if feature in df.columns:
                series = df[feature].dropna()
                plot_acf(series, ax=ax, lags=lags, title='')
                ax.set_title(f'{feature.replace("_", " ").title()} - Autocorrelation')
                ax.grid(True, alpha=0.3)
                
        plt.tight_layout()
        
        if save_path:
            self._save_plot(fig, save_path)
            
        return fig
    
    def generate_summary_stats(self, df: pd.DataFrame) -> Dict:
        """
        Generate comprehensive statistical summary.
        
        Args:
            df: Input DataFrame
            
        Returns:
            Dictionary of summary statistics
        """
        features = self.config['analysis']['features']
        summary = {}
        
        for feature in features:
            if feature not in df.columns:
                continue
                
            series = df[feature].dropna()
            
            # Basic stats
            basic_stats = series.describe()
            
            # Additional metrics
            additional_stats = {
                'variance': series.var(),
                'skewness': series.skew(),
                'kurtosis': series.kurtosis(),
                'range': series.max() - series.min(),
                'iqr': series.quantile(0.75) - series.quantile(0.25),
                'cv': series.std() / series.mean() if series.mean() != 0 else np.nan,  # Coefficient of variation
                'autocorr_lag1': series.autocorr(lag=1) if len(series) > 1 else np.nan
            }
            
            # Trend analysis
            trends = self.detect_trends(df, [feature])
            trend_stats = trends.get(feature, {})
            
            summary[feature] = {
                'basic_stats': basic_stats.to_dict(),
                'additional_stats': additional_stats,
                'trend_analysis': trend_stats
            }
            
        return summary
    
    def run_full_analysis(self, output_dir: str = None) -> Dict:
        """
        Run complete analysis suite with unique filenames and run comparison.
        
        Args:
            output_dir: Directory to save outputs
            
        Returns:
            Dictionary of analysis results
        """
        if output_dir is None:
            output_dir = self.config['plotting']['output_dir']
            
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Add timestamp to ensure unique filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        results = {}
        run_names = list(self.data.keys())
        
        # Individual run analysis
        for run_name, df in self.data.items():
            print(f"\nAnalyzing {run_name}...")
            print(f"Data shape: {df.shape}")
            print(f"Columns: {list(df.columns)}")
            
            # Sanitize run_name for filename
            safe_run_name = run_name.replace('.', '_').replace('-', '_')
            
            # Generate individual plots
            if self.config['plotting']['grid_plots']['enabled']:
                try:
                    plot_filename = f"{safe_run_name}_{timestamp}_time_series_grid"
                    grid_plot = self.plot_time_series_grid_plotly(
                        {run_name: df}, 
                        save_path=output_path / plot_filename
                    )
                    print(f"Generated grid plot: {plot_filename}.html")
                except Exception as e:
                    print(f"Error generating grid plot: {e}")
                        
            try:
                plot_filename = f"{safe_run_name}_{timestamp}_rolling_stats"
                rolling_plot = self.plot_rolling_stats_plotly(
                    df, 
                    save_path=output_path / plot_filename
                )
                print(f"Generated rolling stats plot: {plot_filename}.html")
            except Exception as e:
                print(f"Error generating rolling stats plot: {e}")
                    
            if self.config['analysis']['autocorrelation']:
                try:
                    plot_filename = f"{safe_run_name}_{timestamp}_autocorrelation"
                    autocorr_plot = self.plot_autocorrelation_plotly(
                        df,
                        save_path=output_path / plot_filename
                    )
                    print(f"Generated autocorrelation plot: {plot_filename}.html")
                except Exception as e:
                    print(f"Error generating autocorrelation plot: {e}")
                        
            # Generate statistics
            try:
                stats = self.generate_summary_stats(df)
                results[run_name] = stats
                print(f"Generated statistics for {run_name}")
            except Exception as e:
                print(f"Error generating statistics: {e}")
                results[run_name] = {}
        
            # Run comparison if multiple runs available
            if len(run_names) > 1:
                print(f"\nComparing {len(run_names)} runs...")
                
                try:
                    comparison_filename = f"run_comparison_{timestamp}_time_series_grid"
                    comparison_plot = self.plot_time_series_grid_plotly(
                        self.data,  # Pass all data for comparison
                        save_path=output_path / comparison_filename
                    )
                    print(f"Generated comparison plot: {comparison_filename}.html")
                except Exception as e:
                    print(f"Error generating comparison plot: {e}")
                    
                # Compare specific features
                for feature in self.config['analysis']['features']:
                    try:
                        comparison_filename = f"run_comparison_{timestamp}_{feature}_comparison"
                        feature_comparison = self.compare_runs(
                            run_names=run_names,
                            features=[feature],
                            save_path=output_path / comparison_filename
                        )
                        print(f"Generated feature comparison: {comparison_filename}.html")
                    except Exception as e:
                        print(f"Error generating {feature} comparison: {e}")
            
            # Save summary statistics
            if self.config['export']['save_stats']:
                stats_file = Path(self.config['export']['stats_file'])
                stats_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(stats_file, 'w') as f:
                    json.dump(results, f, indent=2, default=str)
                    
            self.analysis_results = results
            return results
    
    def _save_plot(self, fig, save_path: Union[str, Path]):
        """Save plot in specified formats (now includes HTML)."""
        save_path = Path(save_path)
        
        for fmt in self.config['export']['formats']:
            if fmt == 'html':
                html_path = save_path.with_suffix('.html')
                fig.write_html(str(html_path))
                print(f"Saved interactive plot: {html_path}")
            else:
                # For PNG/PDF, convert to matplotlib temporarily
                import matplotlib.pyplot as plt
                # This is a simplified conversion - you might need to adjust
                img_path = save_path.with_suffix(f'.{fmt}')
                # Note: Converting Plotly to matplotlib is complex, 
                # so for now we'll keep PNG/PDF generation separate
                print(f"Static {fmt.upper()} export not yet implemented for Plotly")
    
    def plot_time_series_grid_plotly(self, data_dict: Dict[str, pd.DataFrame] = None, 
                                   save_path: str = None) -> go.Figure:
        """
        Create an interactive grid of time series plots using Plotly.
        
        Args:
            data_dict: Dictionary of DataFrames (one per run)
            save_path: Path to save plot
            
        Returns:
            Plotly figure object
        """
        if data_dict is None:
            data_dict = self.data
            
        if not data_dict:
            raise ValueError("No data loaded. Call load_data() first.")
            
        features = self.config['analysis']['features']
        n_cols = self.config['plotting']['grid_plots']['n_cols']
        n_features = len(features)
        n_rows = (n_features + n_cols - 1) // n_cols
        
        # Create subplot grid
        fig = make_subplots(
            rows=n_rows, cols=n_cols,
            subplot_titles=[f.replace('_', ' ').title() for f in features],
            shared_xaxes=True
        )
        
        for i, feature in enumerate(features):
            row = i // n_cols + 1
            col = i % n_cols + 1
            
            for run_name, df in data_dict.items():
                if feature in df.columns:
                    series = df[feature].dropna()
                    fig.add_trace(
                        go.Scatter(
                            x=series.index,
                            y=series.values,
                            mode='lines',
                            name=f"{run_name} - {feature}" if len(data_dict) > 1 else feature,
                            line=dict(width=2),
                            hovertemplate=f"{run_name}<br>Month: %{{x}}<br>{feature}: %{{y:.2f}}<extra></extra>"
                        ),
                        row=row, col=col
                    )
            
            # Update axis labels
            fig.update_xaxes(title_text="Month", row=row, col=col)
            fig.update_yaxes(title_text="Value", row=row, col=col)
        
        # Update layout
        fig.update_layout(
            height=400 * n_rows,
            title_text="Time Series Analysis",
            showlegend=len(data_dict) > 1
        )
        
        if save_path:
            html_path = Path(save_path).with_suffix('.html')
            fig.write_html(str(html_path))
            print(f"Saved interactive plot: {html_path}")
            
        return fig
    
    def plot_rolling_stats_plotly(self, df: pd.DataFrame, features: List[str] = None,
                                save_path: str = None) -> go.Figure:
        """
        Create interactive rolling statistics plots with confidence bands.
        
        Args:
            df: Input DataFrame
            features: Features to plot
            save_path: Path to save plot
            
        Returns:
            Plotly figure object
        """
        if features is None:
            features = self.config['analysis']['features']
            
        rolling_stats = self.compute_rolling_stats(df, features)
        
        n_features = len(features)
        fig = make_subplots(
            rows=n_features, cols=1,
            subplot_titles=[f"{f.replace('_', ' ').title()} - Rolling Statistics" for f in features],
            shared_xaxes=True
        )
        
        for i, feature in enumerate(features):
            row = i + 1
            stats_df = rolling_stats[feature]
            
            # Raw data
            fig.add_trace(
                go.Scatter(
                    x=stats_df.index,
                    y=stats_df[f'{feature}_raw'],
                    mode='lines',
                    name=f'{feature} (raw)',
                    line=dict(color='lightgray', width=1),
                    opacity=0.6,
                    showlegend=(i == 0)
                ),
                row=row, col=1
            )
            
            # Rolling mean
            if self.config['plotting']['rolling_stats']['show_mean']:
                fig.add_trace(
                    go.Scatter(
                        x=stats_df.index,
                        y=stats_df[f'{feature}_mean'],
                        mode='lines',
                        name=f'{feature} (mean)',
                        line=dict(color='blue', width=3),
                        showlegend=(i == 0)
                    ),
                    row=row, col=1
                )
                
            # Confidence bands
            if self.config['plotting']['rolling_stats']['show_std']:
                fig.add_trace(
                    go.Scatter(
                        x=stats_df.index,
                        y=stats_df[f'{feature}_upper'],
                        mode='lines',
                        line=dict(width=0),
                        showlegend=False,
                        hoverinfo='skip'
                    ),
                    row=row, col=1
                )
                fig.add_trace(
                    go.Scatter(
                        x=stats_df.index,
                        y=stats_df[f'{feature}_lower'],
                        mode='lines',
                        line=dict(width=0),
                        fill='tonexty',
                        fillcolor='rgba(0,100,255,0.2)',
                        name=f'{feature} (±std)',
                        showlegend=(i == 0)
                    ),
                    row=row, col=1
                )
                
            # Trend line
            if self.config['analysis']['trend_analysis'] and self.config['plotting']['rolling_stats']['show_trend']:
                trends = self.detect_trends(df, [feature])
                if feature in trends:
                    trend_data = trends[feature]
                    fig.add_trace(
                        go.Scatter(
                            x=stats_df.index,
                            y=trend_data['trend_line'],
                            mode='lines',
                            name=f'{feature} (trend)',
                            line=dict(color='red', width=2, dash='dash'),
                            showlegend=(i == 0)
                        ),
                        row=row, col=1
                    )
                    
        fig.update_layout(
            height=300 * n_features,
            title_text="Rolling Statistics Analysis"
        )
        
        if save_path:
            html_path = Path(save_path).with_suffix('.html')
            fig.write_html(str(html_path))
            print(f"Saved interactive plot: {html_path}")
            
        return fig
    
    def plot_autocorrelation_plotly(self, df: pd.DataFrame, features: List[str] = None,
                                  save_path: str = None) -> go.Figure:
        """
        Create interactive autocorrelation plots using Plotly.
        
        Args:
            df: Input DataFrame
            features: Features to analyze
            save_path: Path to save plot
            
        Returns:
            Plotly figure object
        """
        if features is None:
            features = self.config['analysis']['features']
            
        n_features = len(features)
        fig = make_subplots(
            rows=n_features, cols=1,
            subplot_titles=[f"{f.replace('_', ' ').title()} - Autocorrelation" for f in features]
        )
        
        for i, feature in enumerate(features):
            row = i + 1
            
            if feature in df.columns:
                series = df[feature].dropna()
                
                # Compute autocorrelation
                autocorr = [series.autocorr(lag=l) for l in range(25)]  # 24 lags
                
                # Confidence interval (approximate)
                n = len(series)
                conf_interval = 1.96 / np.sqrt(n)
                
                # Plot autocorrelation
                fig.add_trace(
                    go.Bar(
                        x=list(range(25)),
                        y=autocorr,
                        name=feature,
                        showlegend=False,
                        marker_color=['red' if abs(ac) > conf_interval else 'blue' for ac in autocorr]
                    ),
                    row=row, col=1
                )
                
                # Add confidence bands
                fig.add_hline(y=conf_interval, line_dash="dash", line_color="gray", row=row, col=1)
                fig.add_hline(y=-conf_interval, line_dash="dash", line_color="gray", row=row, col=1)
                
            fig.update_xaxes(title_text="Lag", row=row, col=1)
            fig.update_yaxes(title_text="Autocorrelation", row=row, col=1)
            
        fig.update_layout(
            height=300 * n_features,
            title_text="Autocorrelation Analysis",
            showlegend=False
        )
        
        if save_path:
            html_path = Path(save_path).with_suffix('.html')
            fig.write_html(str(html_path))
            print(f"Saved interactive plot: {html_path}")
            
        return fig
    


def main():
    """Main entry point with command-line arguments."""
    
    parser = argparse.ArgumentParser(description='Time Series Analysis for Proxima')
    parser.add_argument('--config', '-c', type=str, 
                       default='complexity_engine/time_series_config.yaml',
                       help='Path to configuration YAML file')
    parser.add_argument('--log-path', '-l', type=str,
                       help='Path to log files directory (overrides config)')
    parser.add_argument('--output-dir', '-o', type=str,
                       help='Output directory for plots and stats (overrides config)')
    parser.add_argument('--features', '-f', nargs='+',
                       help='Features to analyze (overrides config)')
    
    args = parser.parse_args()
    
    # Load base config
    try:
        analyzer = TimeSeriesAnalyzer(args.config)
        print(f"Loaded config from: {args.config}")
    except FileNotFoundError:
        print(f"Config file not found: {args.config}")
        print("Using default configuration...")
        analyzer = TimeSeriesAnalyzer()
    
    # Override with command-line arguments
    if args.log_path:
        analyzer.config['data']['input_dir'] = args.log_path
        print(f"Using log path: {args.log_path}")
    
    if args.output_dir:
        analyzer.config['plotting']['output_dir'] = args.output_dir
        analyzer.config['export']['stats_file'] = f"{args.output_dir}/stats_summary.json"
        print(f"Using output directory: {args.output_dir}")
    
    if args.features:
        analyzer.config['analysis']['features'] = args.features
        print(f"Analyzing features: {args.features}")
    
    # Load data
    analyzer.load_data()
    
    if not analyzer.data:
        print("ERROR: No data loaded!")
        print("Please check:")
        print("1. Log files exist in the specified directory")
        print("2. Files have .csv extension")
        print("3. Files contain the expected 'month' column")
        return 1
    
    # Run full analysis
    results = analyzer.run_full_analysis()
    
    print("\nAnalysis complete!")
    print(f"Results saved to: {analyzer.config['export']['stats_file']}")
    print(f"Plots saved to: {analyzer.config['plotting']['output_dir']}")
    
    # List generated files
    output_dir = Path(analyzer.config['plotting']['output_dir'])
    if output_dir.exists():
        html_files = list(output_dir.glob("*.html"))
        print(f"\nGenerated {len(html_files)} HTML plot files:")
        for f in sorted(html_files):
            print(f"  - {f.name}")
    
    return 0

if __name__ == "__main__":
    exit(main())