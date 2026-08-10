"""
ui_models.py

PROXIMA LUNAR SIMULATION - UI DATA MODELS AND CONFIGURATION

PURPOSE:
========
Centralized configuration, enums, and dataclasses for the Proxima UI dashboard.
Provides type-safe data structures and constants for styling and data management.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Any, List, Optional, Set
import pandas as pd
import yaml
import os


class SectorName(Enum):
    """Available simulation sectors."""

    ENERGY = "energy"
    SCIENCE = "science"
    MANUFACTURING = "manufacturing"
    EQUIPMENT_MANUFACTURING = "equipment_manufacturing"
    TRANSPORTATION = "transportation"
    ENVIRONMENT = "environment"
    CONSTRUCTION = "construction"
    PERFORMANCE = "performance"


class MetricStatus(Enum):
    """Metric threshold status."""

    WITHIN = "within"
    OUTSIDE = "outside"
    UNKNOWN = "unknown"


class SimulationState(Enum):
    """Simulation operational states."""

    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    OFFLINE = "offline"


class CommandAction(Enum):
    """Available simulation commands."""

    START_CONTINUOUS = "start_continuous"
    START_LIMITED = "start_limited"
    PAUSE = "pause"
    RESUME = "resume"
    STOP = "stop"
    SET_DELAY = "set_delay"


@dataclass
class SectorConfig:
    """Configuration for a single sector."""

    id: str  # Internal ID (matches SectorName enum value)
    display_name: str  # Human-readable name for UI
    icon: str  # Emoji or icon
    color: str  # Badge/highlight color
    enabled: bool = True  # Whether to display this sector
    badge_format: Optional[str] = None  # Format string for badge (e.g., "{key}: {value}")
    primary_metrics: List[str] = field(default_factory=list)  # Key metrics to highlight

    def __post_init__(self):
        """Validate sector configuration."""
        if not self.id:
            raise ValueError("Sector id cannot be empty")
        if not self.display_name:
            self.display_name = self.id.replace("_", " ").title()


@dataclass
class SectorRegistry:
    """Registry of all available sectors with configuration."""

    sectors: Dict[str, SectorConfig] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize default sector configurations if empty."""
        if not self.sectors:
            self._initialize_default_sectors()

    def _initialize_default_sectors(self):
        """Setup default sector configurations."""
        self.sectors = {
            SectorName.ENERGY.value: SectorConfig(
                id=SectorName.ENERGY.value,
                display_name="Energy",
                icon="PWR",
                color="#4dffa6",
                badge_format="PWR: {total_power_supply_kW:.1f}/{total_power_need_kW:.1f} kW",
                # primary_metrics=["total_power_supply_kW", "total_charge_level_kwh"],
            ),
            SectorName.SCIENCE.value: SectorConfig(
                id=SectorName.SCIENCE.value,
                display_name="Science",
                icon="SCI",
                color="#4fd8ec",
                badge_format="SCI: {operational_rovers} rovers | {science_generated:.2f}",
            ),
            SectorName.MANUFACTURING.value: SectorConfig(
                id=SectorName.MANUFACTURING.value,
                display_name="Manufacturing",
                icon="MFG",
                color="#5fc2c9",
                badge_format="MFG: {active_operations} ops | {sector_state}",
            ),
            SectorName.EQUIPMENT_MANUFACTURING.value: SectorConfig(
                id=SectorName.EQUIPMENT_MANUFACTURING.value,
                display_name="Equipment Manufacturing",
                icon="EQP",
                color="#a685ff",
                enabled=True,  # Set to False to hide from UI
                badge_format="EQP: {equipment_Science_Rover_EQ} rover eq | {equipment_Assembly_Robot_EQ} assembly eq",
            ),
            SectorName.TRANSPORTATION.value: SectorConfig(
                id=SectorName.TRANSPORTATION.value,
                display_name="Transportation",
                icon="TRN",
                color="#ffb454",
                enabled=True,
                badge_format="TRN: {rockets} rockets | {queued_requests} queued",
            ),
            SectorName.ENVIRONMENT.value: SectorConfig(
                id=SectorName.ENVIRONMENT.value,
                display_name="System",
                icon="ENV",
                color="#6fd6a8",
            ),
            SectorName.CONSTRUCTION.value: SectorConfig(
                id=SectorName.CONSTRUCTION.value,
                display_name="Construction",
                icon="CON",
                color="#c9a4ff",
                badge_format="CON: {shells_in_stock} shells , Working Assembly: {assembly_robots_working}",
            ),
            SectorName.PERFORMANCE.value: SectorConfig(
                id=SectorName.PERFORMANCE.value,
                display_name="Performance",
                icon="PRF",
                color="#ff5a5f",
                enabled=False,  # Usually handled separately
            ),
        }

    def get_sector(self, sector_id: str) -> Optional[SectorConfig]:
        """Get sector configuration by ID."""
        return self.sectors.get(sector_id)

    def get_enabled_sectors(self) -> List[SectorConfig]:
        """Get all enabled sectors."""
        return [s for s in self.sectors.values() if s.enabled]

    def get_table_sectors(self) -> List[SectorConfig]:
        """Get sectors to display in the sector details table."""
        # Exclude performance as it's shown separately
        return [s for s in self.sectors.values() if s.enabled and s.id != SectorName.PERFORMANCE.value]

    def get_badge_sectors(self) -> List[SectorConfig]:
        """Get sectors to display as status badges."""
        return [s for s in self.sectors.values() if s.enabled and s.badge_format]

    def add_sector(self, config: SectorConfig) -> None:
        """Add or update a sector configuration."""
        self.sectors[config.id] = config

    def remove_sector(self, sector_id: str) -> None:
        """Remove a sector from the registry."""
        self.sectors.pop(sector_id, None)


@dataclass
class BadgeConfig:
    """Configuration for custom status badges (non-sector badges)."""

    id: str
    display_name: str
    format_string: str  # e.g., "🌪️ DUST: {score:.2f}"
    color_map: Dict[str, str] = field(default_factory=dict)  # status -> color mapping
    default_color: str = "#6c757d"

    def get_color(self, status: str) -> str:
        """Get color for a given status."""
        return self.color_map.get(status, self.default_color)


@dataclass
class BadgeRegistry:
    """Registry of custom badges (non-sector)."""

    badges: Dict[str, BadgeConfig] = field(default_factory=dict)

    def get_badge(self, badge_id: str) -> Optional[BadgeConfig]:
        """Get badge configuration by ID."""
        return self.badges.get(badge_id)

    def add_badge(self, config: BadgeConfig) -> None:
        """Add or update a badge configuration."""
        self.badges[config.id] = config


@dataclass
class MetricCategory:
    """Metric category for filtering."""

    id: str
    display_name: str
    icon: str
    color: str
    metric_patterns: List[str] = field(default_factory=list)  # Patterns to match metric names


@dataclass
class MetricFilterConfig:
    """Configuration for metric filtering."""

    categories: Dict[str, MetricCategory] = field(default_factory=dict)

    def __post_init__(self):
        if not self.categories:
            self._initialize_default_categories()

    def _initialize_default_categories(self):
        """Setup default metric categories."""
        self.categories = {
            "energy": MetricCategory(
                id="energy",
                display_name="Energy & Power",
                icon="PWR",
                color="#4dffa6",
                metric_patterns=["energy_", "power_", "battery_", "charge_"],
            ),
            "science": MetricCategory(
                id="science",
                display_name="Science & Research",
                icon="SCI",
                color="#4fd8ec",
                metric_patterns=["science_", "research_", "experiment_", "rover"],
            ),
            "manufacturing": MetricCategory(
                id="manufacturing",
                display_name="Manufacturing",
                icon="MFG",
                color="#a685ff",
                metric_patterns=["manufacturing_", "production_", "equipment_"],
            ),
            "environment": MetricCategory(
                id="environment",
                display_name="Environment",
                icon="ENV",
                color="#6fd6a8",
                metric_patterns=["environment_", "temperature_", "pressure_", "atmosphere_"],
            ),
            "transportation": MetricCategory(
                id="transportation",
                display_name="Transportation",
                icon="TRN",
                color="#ffb454",
                metric_patterns=["transportation_", "vehicle_", "mission_"],
            ),
            "construction": MetricCategory(
                id="construction",
                display_name="Construction",
                icon="CON",
                color="#c9a4ff",
                metric_patterns=["construction_", "module_", "shell_", "robot_"],
            ),
        }

    def categorize_metric(self, metric_name: str) -> str:
        """Determine which category a metric belongs to."""
        for cat_id, category in self.categories.items():
            for pattern in category.metric_patterns:
                if metric_name.startswith(pattern):
                    return cat_id
        return "other"

    def get_metrics_by_category(self, all_metrics: List[str]) -> Dict[str, List[str]]:
        """Group metrics by category."""
        categorized = {cat_id: [] for cat_id in self.categories.keys()}
        categorized["other"] = []

        for metric in all_metrics:
            cat = self.categorize_metric(metric)
            categorized[cat].append(metric)

        return categorized


@dataclass
class UIColors:
    """UI color palette - Mission Control HUD theme."""

    primary: str = "#4fd8ec"
    success: str = "#4dffa6"
    warning: str = "#ffb454"
    danger: str = "#ff5a5f"
    info: str = "#4fd8ec"
    secondary: str = "#6d8991"

    # Extended palette for charts - cyan/amber/violet HUD accents
    chart_colors: List[str] = field(
        default_factory=lambda: [
            "#4fd8ec",
            "#ffb454",
            "#4dffa6",
            "#a685ff",
            "#ff5a5f",
            "#8ff2ff",
            "#e8e8e8",
            "#6d8991",
        ]
    )


@dataclass
class DarkTheme:
    """Mission-control dark theme configuration."""

    bg_primary: str = "#05090b"
    bg_secondary: str = "#0b141a"
    bg_tertiary: str = "#0a1318"
    border: str = "rgba(112,213,232,0.22)"
    text: str = "#d7f2f6"
    text_muted: str = "#6d8991"

    # HUD accent colors
    accent: str = "#4fd8ec"
    accent_bright: str = "#8ff2ff"
    accent_dim: str = "rgba(79,216,236,0.35)"
    amber: str = "#ffb454"
    red: str = "#ff5a5f"
    green: str = "#4dffa6"
    font_display: str = "'Orbitron', 'Arial Narrow', sans-serif"
    font_body: str = "'Rajdhani', 'Segoe UI', sans-serif"
    font_mono: str = "'Share Tech Mono', 'SFMono-Regular', Consolas, monospace"


@dataclass
class UIConfig:
    """UI configuration settings."""

    experiment_id: str
    update_rate_ms: int = 1000
    update_cycles: int = 1
    ts_data_count: int = 200
    read_only: bool = True
    default_step_delay: float = 0.1
    default_max_steps: int = 100

    # Sector and badge registries
    sector_registry: SectorRegistry = field(default_factory=SectorRegistry)
    badge_registry: BadgeRegistry = field(default_factory=BadgeRegistry)
    metric_filter_config: MetricFilterConfig = field(default_factory=MetricFilterConfig)  # Add this

    def __post_init__(self):
        """Validate configuration."""
        if self.update_rate_ms <= 0:
            raise ValueError("update_rate_ms must be positive")
        if self.ts_data_count <= 0:
            raise ValueError("ts_data_count must be positive")


@dataclass
class MetricDefinition:
    """Performance metric definition."""

    id: str
    name: str
    unit: Optional[str] = None
    type: str = "positive"
    threshold_low: float = 0.0
    threshold_high: float = 1.0
    current: float = 0.0
    score: Optional[float] = None
    status: str = MetricStatus.UNKNOWN.value
    goal: Optional[Dict[str, Any]] = None

    @classmethod
    def from_score_entry(cls, metric_id: str, entry: Dict[str, Any]) -> "MetricDefinition":
        """Create from score entry dictionary."""
        return cls(
            id=metric_id,
            name=entry.get("name", metric_id),
            unit=entry.get("unit"),
            type=entry.get("type", "positive"),
            threshold_low=float(entry.get("threshold_low", 0.0)),
            threshold_high=float(entry.get("threshold_high", 1.0)),
            current=float(entry.get("current", 0.0)),
            score=entry.get("score"),
            status=entry.get("status", MetricStatus.UNKNOWN.value),
            goal=entry.get("goal"),
        )

    def get_status_color(self) -> str:
        """Get badge color based on status."""
        color_map = {
            MetricStatus.WITHIN.value: "success",
            MetricStatus.OUTSIDE.value: "danger",
            MetricStatus.UNKNOWN.value: "warning",
        }
        return color_map.get(self.status, "secondary")


@dataclass
class SectorData:
    """Sector data for table display."""

    sector: str
    metric: str
    value: str
    _id: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for AG Grid."""
        return {"Sector": self.sector, "Metric": self.metric, "Value": self.value, "_id": self._id}


@dataclass
class BadgeData:
    """Status badge information."""

    text: str
    color: str

    @staticmethod
    def format_badge(format_string: str, data: Dict[str, Any], color: str) -> "BadgeData":
        """
        Format a badge using a format string and data dictionary.

        Args:
            format_string: Format string with {key} placeholders
            data: Dictionary with values to format
            color: Badge color

        Returns:
            BadgeData instance
        """
        try:
            text = format_string.format(**data)
        except (KeyError, ValueError, TypeError):
            # Fallback if formatting fails
            text = format_string

        return BadgeData(text, color)

    @staticmethod
    def create_default(icon: str = "❓") -> "BadgeData":
        """Create a default/offline badge."""
        return BadgeData(f"{icon} -", "#6c757d")


@dataclass
class DashboardStatus:
    """Complete dashboard status."""

    status_text: str
    badges: Dict[str, BadgeData]

    @staticmethod
    def create_offline() -> "DashboardStatus":
        """Create offline status."""
        return DashboardStatus(status_text="🔴 OFFLINE - Sol 0", badges={})


class DataFrameProcessor:
    """Processes log documents into DataFrames."""

    @staticmethod
    def load_experiment_metrics_config() -> Dict[str, Any]:
        """Load experiment-specific metrics config from YAML file."""
        config_path = os.path.join(
            os.path.dirname(__file__), "config", "experiment_metrics.yaml"
        )
        
        if not os.path.exists(config_path):
            return {"default": {"plot_metrics": []}}
        
        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f) or {"default": {"plot_metrics": []}}
        except Exception as e:
            print(f"⚠️ Failed to load experiment metrics config: {e}")
            return {"default": {"plot_metrics": []}}

    @staticmethod
    def flatten_logs_to_dataframe(docs: List[Dict[str, Any]]) -> Optional[pd.DataFrame]:
        """Convert log documents to flattened DataFrame."""
        if not docs:
            return None

        flat_rows = []
        for doc in docs:
            row = {
                "experiment_id": doc.get("experiment_id"),
                "step": doc.get("step"),
                "timestamp": doc.get("timestamp"),
            }

            for key, value in doc.items():
                if key in ("experiment_id", "step", "timestamp"):
                    continue

                if isinstance(value, dict):
                    if key == "performance":
                        DataFrameProcessor._extract_performance_data(value, row)
                    else:
                        # Flatten other nested dicts
                        for subkey, subvalue in value.items():
                            row[f"{key}_{subkey}"] = subvalue
                else:
                    row[key] = value

            flat_rows.append(row)

        try:
            return pd.DataFrame(flat_rows)
        except Exception as e:
            print(f"❌ DataFrame build error: {e}")
            return None

    @staticmethod
    def _extract_performance_data(perf_data: Dict[str, Any], row: Dict[str, Any]) -> None:
        """Extract performance metrics and scores."""
        # Extract metrics
        metrics = perf_data.get("metrics", {})
        if isinstance(metrics, dict):
            for metric_id, metric_value in metrics.items():
                row[f"metric_{metric_id}"] = metric_value

        # Extract scores
        scores = perf_data.get("scores", {})
        if isinstance(scores, dict):
            for metric_id, entry in scores.items():
                try:
                    row[f"score_{metric_id}"] = float(entry.get("score", None))
                except (TypeError, ValueError):
                    pass

    @staticmethod
    def get_numeric_columns(df: pd.DataFrame) -> List[str]:
        """Get numeric columns suitable for plotting."""
        if df is None or df.empty:
            return []

        return [
            col
            for col in df.columns
            if col not in ["step", "timestamp", "experiment_id"]
            and not col.startswith(("metric_", "score_"))
            and pd.api.types.is_numeric_dtype(df[col])
        ]

    @staticmethod
    def get_default_metrics(available_columns: List[str], experiment_id: str = "default") -> List[str]:
        """Get default metrics for initial selection, prioritizing experiment config."""
        # Load experiment-specific config
        config = DataFrameProcessor.load_experiment_metrics_config()
        experiment_config = config.get(experiment_id) or config.get("default")
        
        if experiment_config and experiment_config.get("plot_metrics"):
            # Use experiment-specific metrics, filter to available columns
            configured_metrics = experiment_config.get("plot_metrics", [])
            chosen = [m for m in configured_metrics if m in available_columns]
            if chosen:
                return chosen[:8]  # Max 8 metrics on plot
        
        # Fallback to hardcoded defaults
        preferred = [
            "energy_total_power_supply_kw",
            "energy_total_charge_level_kwh",
            "science_science_generated",
            "science_operational_rovers",
        ]

        chosen = [m for m in preferred if m in available_columns][:4]

        # Fill remaining slots
        for col in available_columns:
            if len(chosen) >= 4:
                break
            if col not in chosen:
                chosen.append(col)

        return chosen[:4]
