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

    def log(self, step, model_metrics, agent_metrics, latest_state):
        """Log simulation data to both CSV and database."""
        timestamp = self._generate_timestamp(step)

        # Extract only the key metrics for time-series (no nested objects)
        microgrid = latest_state.get("microgrid", {})
        ws_metrics = latest_state.get("ws_metrics", {})
        science_rovers = latest_state.get("science_rovers", [])
        
        # Flatten to simple key-value pairs only
        log_entry = {
            "experiment_id": self.experiment_id,
            "step": step,
            "timestamp": timestamp,
            
            # World metrics
            "daylight": ws_metrics.get("Daylight", 0),
            "science_generated": ws_metrics.get("science_generated", 0),
            
            # Microgrid metrics  
            "total_power_supply_kW": microgrid.get("total_power_supply_kW", 0),
            "total_power_need_kW": microgrid.get("total_power_need_kW", 0),
            "total_charge_level_kWh": microgrid.get("total_charge_level_kWh", 0),
            "total_state_of_charge_%": microgrid.get("total_state_of_charge_%", 0),
            "total_charge_capacity_kWh": microgrid.get("total_charge_capacity_kWh", 0),
            
            # Rover metrics (aggregated)
            "active_rovers": len([r for r in science_rovers if r.get("is_operational", False)]),
            "total_rovers": len(science_rovers),
            "avg_rover_battery": sum(r.get("battery_kWh", 0) for r in science_rovers) / len(science_rovers) if science_rovers else 0,
        }

        if self.log_to_db:
            # Use insert_one for time-series collections (append-only)
            try:
                self.db.db["logs_simulation"].insert_one(log_entry)
            except Exception as e:
                print(f"⚠️  Warning: Could not insert log entry for step {step}: {e}")

            # Also update world system latest_state (for UI snapshots)
            self.db.db["world_systems"].update_one(
                {"_id": self.ws_id},
                {"$set": {"latest_state": latest_state}},
            )

        # Add to CSV records (clean time-series data only)
        if self.log_to_csv:
            self.records.append(log_entry)

    def save_to_file(self):
        if self.log_to_csv and self.records:
            df = pd.DataFrame(self.records)
            df.to_csv(self.csv_path, index=False)
            print(f"📄 Log saved to {self.csv_path}")

    def create_unique_index(self):
        """Create unique index to prevent duplicates - run once."""
        try:
            self.db.db["logs_simulation"].create_index(
                [("experiment_id", 1), ("step", 1)], 
                unique=True
            )
            print("✅ Created unique index on logs_simulation collection")
        except Exception as e:
            print(f"ℹ️  Index may already exist: {e}")
