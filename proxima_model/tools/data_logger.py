"""
data_logger.py

PROXIMA LUNAR SIMULATION - DATA LOGGER

PURPOSE:
========
Handles simulation data logging to CSV files and MongoDB database.
Maintains structured logs with sector organization and automatic timestamp generation.

FEATURES:
=========
- Dual output: CSV files and MongoDB time-series collection
- Automatic log clearing on initialization
- Nested sector data with automatic flattening for CSV
- World system state updates
- Configurable logging targets
"""

from __future__ import annotations
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Any, Optional
from data_engine.proxima_db_engine import ProximaDB


class LogLevel(Enum):
    """Log verbosity levels."""

    DEBUG = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()


class LogDestination(Enum):
    """Available logging destinations."""

    CSV = "csv"
    DATABASE = "database"
    BOTH = "both"


@dataclass
class LoggerConfig:
    """Configuration for data logger."""

    experiment_id: str
    ws_id: str
    log_dir: str = "log_files"
    log_to_csv: bool = True
    log_to_db: bool = True
    base_time: Optional[datetime] = None

    def __post_init__(self):
        """Validate configuration."""
        if not self.experiment_id:
            raise ValueError("experiment_id cannot be empty")
        if not self.ws_id:
            raise ValueError("ws_id cannot be empty")

        # Set default base time if not provided
        if self.base_time is None:
            self.base_time = datetime.now(timezone.utc)


@dataclass
class LogEntry:
    """Represents a single log entry."""

    experiment_id: str
    step: int
    timestamp: datetime
    sector_data: Dict[str, Any] = field(default_factory=dict)
    latest_state: Optional[Dict[str, Any]] = None

    def to_db_document(self) -> Dict[str, Any]:
        """Convert to MongoDB document format."""
        doc = {
            "experiment_id": self.experiment_id,
            "step": self.step,
            "timestamp": self.timestamp,
        }
        # Add all sector data directly
        doc.update(self.sector_data)
        return doc

    def to_flat_record(self) -> Dict[str, Any]:
        """Convert to flat dictionary for CSV."""
        flat_record = {
            "experiment_id": self.experiment_id,
            "step": self.step,
            "timestamp": self.timestamp,
        }

        # Flatten nested dictionaries
        for sector_name, sector_values in self.sector_data.items():
            if isinstance(sector_values, dict):
                for key, value in sector_values.items():
                    # Special case: performance.metrics expansion
                    if sector_name == "performance" and key == "metrics" and isinstance(value, dict):
                        for metric_id, metric_value in value.items():
                            flat_record[f"metric_{metric_id}"] = metric_value
                    else:
                        flat_record[f"{sector_name}_{key}"] = value
            else:
                flat_record[sector_name] = sector_values

        return flat_record


class DataLogger:
    """
    Manages simulation data logging to CSV and MongoDB.

    Features:
    - Dual logging: CSV files and MongoDB time-series collection
    - Automatic timestamp generation based on simulation steps
    - Nested sector data with flattening for CSV compatibility
    - World system state synchronization
    - Automatic cleanup of previous experiment logs
    """

    # Collection names
    COLLECTION_LOGS = "logs_simulation"
    COLLECTION_WORLD_SYSTEMS = "world_systems"

    def __init__(
        self,
        experiment_id: str,
        db: ProximaDB,
        ws_id: str,
        log_dir: str = "log_files",
        log_to_csv: bool = True,
        log_to_db: bool = True,
    ):
        """
        Initialize data logger with configuration.

        Args:
            experiment_id: Unique identifier for the experiment
            db: ProximaDB database instance
            ws_id: World system ID for state updates
            log_dir: Directory for CSV log files
            log_to_csv: Whether to log to CSV files
            log_to_db: Whether to log to MongoDB
        """
        # Create configuration
        self._config = LoggerConfig(
            experiment_id=experiment_id,
            ws_id=ws_id,
            log_dir=log_dir,
            log_to_csv=log_to_csv,
            log_to_db=log_to_db,
        )

        self.db = db
        self._records: List[Dict[str, Any]] = []

        # Setup logging directory
        self._log_path = Path(self._config.log_dir)
        self._log_path.mkdir(parents=True, exist_ok=True)

        # Generate CSV filename with timestamp
        timestamp = datetime.now(timezone.utc).timestamp()
        self._csv_path = self._log_path / f"simlog_{experiment_id}_{timestamp}.csv"

        # Clear existing logs for this experiment
        self._clear_existing_logs()

    def _clear_existing_logs(self) -> None:
        """Clear existing logs for this experiment from database."""
        if not self._config.log_to_db:
            return

        try:
            result = self.db.db[self.COLLECTION_LOGS].delete_many({"experiment_id": self._config.experiment_id})
            print(f"🗑️  Cleared {result.deleted_count} existing logs for experiment: {self._config.experiment_id}")
        except Exception as e:
            print(f"⚠️  Could not clear existing logs: {e}")

    def _generate_timestamp(self, step: int) -> datetime:
        """
        Generate timestamp for a given step.

        Args:
            step: Simulation step number

        Returns:
            Datetime representing the step (base_time + step hours)
        """
        return self._config.base_time + timedelta(hours=step)

    def _log_to_database(self, entry: LogEntry) -> None:
        """
        Log entry to MongoDB database.

        Args:
            entry: LogEntry to persist
        """
        if not self._config.log_to_db:
            return

        try:
            # Insert log document
            self.db.db[self.COLLECTION_LOGS].insert_one(entry.to_db_document())

            # Update world system state if provided
            if entry.latest_state:
                complete_state = {**entry.latest_state, "sectors": entry.sector_data}
                self.db.db[self.COLLECTION_WORLD_SYSTEMS].update_one(
                    {"_id": self._config.ws_id},
                    {"$set": {"latest_state": complete_state}},
                )
        except Exception as e:
            print(f"⚠️  Warning: Could not insert log entry for step {entry.step}: {e}")

    def _log_to_csv(self, entry: LogEntry) -> None:
        """
        Add entry to CSV buffer.

        Args:
            entry: LogEntry to buffer for CSV
        """
        if not self._config.log_to_csv:
            return

        self._records.append(entry.to_flat_record())

    def log(self, step: int, **kwargs) -> None:
        """
        Log simulation data with sector organization.

        Args:
            step: Current simulation step
            **kwargs: Sector data and optional latest_state
        """
        # Extract latest_state if present
        latest_state = kwargs.pop("latest_state", None)

        # Create log entry
        entry = LogEntry(
            experiment_id=self._config.experiment_id,
            step=step,
            timestamp=self._generate_timestamp(step),
            sector_data=kwargs,
            latest_state=latest_state,
        )

        # Log to configured destinations
        self._log_to_database(entry)
        self._log_to_csv(entry)

    def save_to_file(self) -> None:
        """Save buffered CSV records to file."""
        if not self._config.log_to_csv or not self._records:
            return

        try:
            df = pd.DataFrame(self._records)
            df.to_csv(self._csv_path, index=False)
            print(f"📄 Log saved to {self._csv_path}")
        except Exception as e:
            print(f"⚠️  Could not save CSV log: {e}")

    def create_unique_index(self) -> None:
        """
        Create unique index on logs collection to prevent duplicates.

        Should be run once during setup. Safe to call multiple times
        (will report if index already exists).
        """
        if not self._config.log_to_db:
            return

        try:
            self.db.db[self.COLLECTION_LOGS].create_index([("experiment_id", 1), ("step", 1)], unique=True)
            print("✅ Created unique index on logs_simulation collection")
        except Exception as e:
            print(f"ℹ️  Index may already exist: {e}")

    def get_config(self) -> LoggerConfig:
        """Get current logger configuration (read-only copy)."""
        return self._config

    def get_record_count(self) -> int:
        """Get number of buffered CSV records."""
        return len(self._records)

    def clear_csv_buffer(self) -> None:
        """Clear buffered CSV records without saving."""
        self._records.clear()
