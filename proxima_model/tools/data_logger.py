import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from data_engine.proxima_db_engine import ProximaDB


class DataLogger:
    def __init__(self, experiment_id, db: ProximaDB, log_dir="log_files", log_to_csv=True, log_to_db=True):
        self.experiment_id = experiment_id
        self.log_to_csv = log_to_csv
        self.log_to_db = log_to_db
        self.db = db
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).timestamp()
        self.csv_path = self.log_dir / f"simlog_{experiment_id}_{timestamp}.csv"

        self.records = []

    def save_to_file(self):
        if self.log_to_csv and self.records:
            df = pd.DataFrame(self.records)
            df.to_csv(self.csv_path, index=False)
            print(f"📄 Log saved to {self.csv_path}")

    def log(self, step: int, model_metrics: dict, agent_metrics: list):
        timestamp = datetime.now(timezone.utc)

        for agent_index, agent_data in enumerate(agent_metrics):
            record = {
                "timestamp": timestamp,
                "step": step,
                "experiment_id": self.experiment_id,
                "agent_index": agent_index,
                **model_metrics,
                **agent_data,
            }

            self.records.append(record)

            if self.log_to_db:
                self.db.log_simulation_step(record)
