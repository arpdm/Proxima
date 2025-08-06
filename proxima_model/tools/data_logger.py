import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from data_engine.proxima_db_engine import ProximaDB


class DataLogger:
    def __init__(self, experiment_id, db: ProximaDB, ws_id, log_dir="log_files", log_to_csv=True, log_to_db=True):
        self.experiment_id = experiment_id
        self.db = db
        self.ws_id = ws_id
        self.log_to_csv = log_to_csv
        self.log_to_db = log_to_db
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).timestamp()
        self.csv_path = self.log_dir / f"simlog_{experiment_id}_{timestamp}.csv"

        self.records = []
        self.base_time = datetime.now(timezone.utc)

        # Clear existing logs for this experiment on initialization
        # Use delete_many for time-series collections
        if self.log_to_db:
            try:
                result = self.db.db["logs_simulation"].delete_many({"experiment_id": self.experiment_id})
                print(f"🗑️  Cleared {result.deleted_count} existing logs for experiment: {self.experiment_id}")
            except Exception as e:
                print(f"⚠️  Could not clear existing logs: {e}")

    def _generate_timestamp(self, step: int) -> datetime:
        return self.base_time + timedelta(hours=step)

    def log(self, step, **kwargs):
        """Log simulation data with sector organization."""
        timestamp = self._generate_timestamp(step)

        # Start with basic metadata
        log_entry = {
            "experiment_id": self.experiment_id,
            "step": step,
            "timestamp": timestamp,
        }

        # Extract latest_state if present
        latest_state = kwargs.pop("latest_state", None)

        # Add sector data directly to log entry
        for sector_name, sector_data in kwargs.items():
            if isinstance(sector_data, dict):
                log_entry[sector_name] = sector_data
            else:
                log_entry[sector_name] = sector_data

        if self.log_to_db:
            # Store nested structure in MongoDB
            try:
                self.db.db["logs_simulation"].insert_one(log_entry)
            except Exception as e:
                print(f"⚠️  Warning: Could not insert log entry for step {step}: {e}")

            # Update world system state
            if latest_state:
                self.db.db["world_systems"].update_one(
                    {"_id": self.ws_id},
                    {"$set": {"latest_state": latest_state}},
                )

        # For CSV, flatten the structure
        if self.log_to_csv:
            flat_record = {
                "experiment_id": self.experiment_id,
                "step": step,
                "timestamp": timestamp,
            }

            # Flatten nested dictionaries for CSV
            for sector_name, sector_data in kwargs.items():
                if isinstance(sector_data, dict):
                    for key, value in sector_data.items():
                        flat_record[f"{sector_name}_{key}"] = value
                else:
                    flat_record[sector_name] = value

            self.records.append(flat_record)

    def save_to_file(self):
        if self.log_to_csv and self.records:
            df = pd.DataFrame(self.records)
            df.to_csv(self.csv_path, index=False)
            print(f"📄 Log saved to {self.csv_path}")

    def create_unique_index(self):
        """Create unique index to prevent duplicates - run once."""
        try:
            self.db.db["logs_simulation"].create_index([("experiment_id", 1), ("step", 1)], unique=True)
            print("✅ Created unique index on logs_simulation collection")
        except Exception as e:
            print(f"ℹ️  Index may already exist: {e}")
