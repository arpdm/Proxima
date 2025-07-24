import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from data_engine.proxima_db_engine import ProximaDB


class DataLogger:
    def __init__(self, experiment_id, db: ProximaDB, log_dir="log_files", log_to_csv=True, log_to_db=True):
        self.experiment_id = experiment_id
        self.db = db
        self.log_to_csv = log_to_csv
        self.log_to_db = log_to_db
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).timestamp()
        self.csv_path = self.log_dir / f"simlog_{experiment_id}_{timestamp}.csv"

        self.records = []
        self.base_time = datetime.now(timezone.utc)

    def _generate_timestamp(self, step: int) -> datetime:
        return self.base_time + timedelta(hours=step)

    def log(self, step: int, model_metrics: dict, agent_metrics: list):
        timestamp = self._generate_timestamp(step)

        doc = {
            "timestamp": timestamp,
            "step": step,
            "experiment_id": self.experiment_id,
            **model_metrics,
            "rover_states": [],
        }

        for entry in agent_metrics:
            # If it's a list of agents (like rovers)
            if isinstance(entry, list):
                for agent in entry:
                    if "science_rover" in agent.get("type", ""):
                        doc["rover_states"].append(agent)
            elif isinstance(entry, dict):
                # If it's a system component like microgrid
                doc.update(entry)

        self.records.append(doc)

        if self.log_to_db:
            self.db.log_simulation_step(doc)

    def save_to_file(self):
        if self.log_to_csv and self.records:
            df = pd.DataFrame(self.records)
            df.to_csv(self.csv_path, index=False)
            print(f"📄 Log saved to {self.csv_path}")
