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


class SectorName(Enum):
    """Available simulation sectors."""

    ENERGY = "energy"
    SCIENCE = "science"
    MANUFACTURING = "manufacturing"
    EQUIPMENT_MANUFACTURING = "equipment_manufacturing"
    TRANSPORTATION = "transportation"
    ENVIRONMENT = "environment"
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
                icon="⚡",
                color="#00FF88",
                badge_format="⚡ PWR: {total_power_supply_kW:.1f}/{total_power_need_kW:.1f} kW",
                primary_metrics=["total_power_supply_kW", "total_charge_level_kwh"],
            ),
            SectorName.SCIENCE.value: SectorConfig(
                id=SectorName.SCIENCE.value,
                display_name="Science",
                icon="🔬",
                color="#0dcaf0",
                badge_format="🔬 SCI: {operational_rovers} rovers | {science_generated:.2f}",
                primary_metrics=["operational_rovers", "science_generated"],
            ),
            SectorName.MANUFACTURING.value: SectorConfig(
                id=SectorName.MANUFACTURING.value,
                display_name="Manufacturing",
                icon="⚙️",
                color="#0dcaf0",
                badge_format="⚙️ MFG: {active_operations} ops | {sector_state}",
                primary_metrics=["active_operations", "sector_state"],
            ),
            SectorName.EQUIPMENT_MANUFACTURING.value: SectorConfig(
                id=SectorName.EQUIPMENT_MANUFACTURING.value,
                display_name="Equipment Manufacturing",
                icon="🔧",
                color="#8b5cf6",
                enabled=True,  # Set to False to hide from UI
                primary_metrics=["production_rate", "inventory_level"],
            ),
            SectorName.TRANSPORTATION.value: SectorConfig(
                id=SectorName.TRANSPORTATION.value,
                display_name="Transportation",
                icon="🚀",
                color="#f59e0b",
                enabled=True,
                primary_metrics=["active_missions", "fuel_level"],
            ),
            SectorName.ENVIRONMENT.value: SectorConfig(
                id=SectorName.ENVIRONMENT.value,
                display_name="System",
                icon="🌍",
                color="#10b981",
                primary_metrics=["step", "simulation_time"],
            ),
            SectorName.PERFORMANCE.value: SectorConfig(
                id=SectorName.PERFORMANCE.value,
                display_name="Performance",
                icon="📊",
                color="#ef4444",
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
                icon="⚡",
                color="#00FF88",
                metric_patterns=["energy_", "power_", "battery_", "charge_"],
            ),
            "science": MetricCategory(
                id="science",
                display_name="Science & Research",
                icon="🔬",
                color="#0dcaf0",
                metric_patterns=["science_", "research_", "experiment_", "rover"],
            ),
            "manufacturing": MetricCategory(
                id="manufacturing",
                display_name="Manufacturing",
                icon="⚙️",
                color="#8b5cf6",
                metric_patterns=["manufacturing_", "production_", "equipment_"],
            ),
            "environment": MetricCategory(
                id="environment",
                display_name="Environment",
                icon="🌍",
                color="#10b981",
                metric_patterns=["environment_", "temperature_", "pressure_", "atmosphere_"],
            ),
            "transportation": MetricCategory(
                id="transportation",
                display_name="Transportation",
                icon="🚀",
                color="#f59e0b",
                metric_patterns=["transportation_", "vehicle_", "mission_"],
            )
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
    """UI color palette."""

    primary: str = "#0d6efd"
    success: str = "#198754"
    warning: str = "#ffc107"
    danger: str = "#dc3545"
    info: str = "#0dcaf0"
    secondary: str = "#6c757d"

    # Extended palette for charts
    chart_colors: List[str] = field(
        default_factory=lambda: ["#00d4aa", "#8b5cf6", "#06b6d4", "#f59e0b", "#10b981", "#ef4444", "#3b82f6", "#f97316"]
    )


@dataclass
class DarkTheme:
    """Dark theme configuration."""

    bg_primary: str = "rgb(25,29,33)"
    bg_secondary: str = "rgb(35,39,43)"
    bg_tertiary: str = "rgb(45,49,53)"
    border: str = "#404040"
    text: str = "#e0e0e0"
    text_muted: str = "#9ca3af"


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
    def get_default_metrics(available_columns: List[str]) -> List[str]:
        """Get default metrics for initial selection."""
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
