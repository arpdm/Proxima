"""
ProximaRunner: Simplified simulation runner with UI command support.
"""

import time
import traceback

from data_engine.proxima_db_engine import ProximaDB
from proxima_model.world_system_builder.world_system_builder import build_world_system_config
from proxima_model.world_system_builder.world_system import WorldSystem
from proxima_model.tools.data_logger import DataLogger


class ProximaRunner:
    def __init__(self):
        self.proxima_db = ProximaDB()
        self.proxima_db.db.db.logs_simulation.delete_many({})  # Clear old logs

        # Get experiment config
        exp_config = self.proxima_db.find_by_id("experiments", "exp_001")
        self.sim_time = exp_config.get("simulation_time_stapes", None)
        self.ws_id = exp_config["world_system_id"]
        self.exp_id = exp_config["_id"]

        # Setup state
        self.logger = DataLogger(experiment_id=self.exp_id, db=self.proxima_db, ws_id=self.ws_id)
        self.is_running = False
        self.is_paused = False
        self.step_delay = 0.1

    def run(self, continuous=None):
        """Main simulation runner."""
        continuous = continuous if continuous is not None else (self.sim_time is None)

        config = build_world_system_config(self.ws_id, self.exp_id, self.proxima_db)
        ws = WorldSystem(config)
        self._reset_state()

        try:
            while self.is_running and (continuous or ws.steps < self.sim_time):
                self._process_commands()

                if self.is_paused:
                    time.sleep(0.1)
                    continue
                if not self.is_running:
                    break

                self._execute_step(ws, continuous)

        except Exception as e:
            print(f"Simulation error: {e}")
            traceback.print_exc()
        finally:
            self._cleanup()

    def _reset_state(self):
        """Reset runner state for new simulation."""
        self.is_running = True
        self.is_paused = False

    def _execute_step(self, ws, continuous):
        """Execute single simulation step."""
        ws.step()

        # GUIDE: Add per sector
        self.logger.log(
            step=ws.steps,
            environment=ws.model_metrics["environment"],
            energy=ws.model_metrics["energy"],
            science=ws.model_metrics["science"],
            manufacturing=ws.model_metrics["manufacturing"],
            performance=ws.model_metrics.get("performance", {}),
            latest_state=self._build_state(ws.steps, continuous),
        )

        time.sleep(self.step_delay)

    def _build_state(self, step, continuous):
        """Build current state object."""
        return {
            "step": step,
            "simulation_status": {
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "step_delay": self.step_delay,
                "mode": "continuous" if continuous else "limited",
                "timestamp": time.time(),
            },
        }

    def _process_commands(self):
        """Process runtime commands."""
        try:
            command = self.proxima_db.db["runtime_commands"].find_one_and_delete(
                {"experiment_id": self.exp_id}, sort=[("timestamp", -1)]
            )

            if not command:
                return

            self._execute_command(command)

        except Exception as e:
            print(f"Command error: {e}")

    def _execute_command(self, command):
        """Execute a single command."""
        action = command.get("action")
        print(f"Processing: {action}")

        command_map = {
            "pause": lambda: setattr(self, "is_paused", True),
            "resume": lambda: setattr(self, "is_paused", False),
            "stop": lambda: setattr(self, "is_running", False),
            "set_delay": lambda: setattr(self, "step_delay", max(0.01, float(command.get("delay", 0.1)))),
        }

        if action in command_map:
            command_map[action]()
            print(f"Applied: {action}")

    def _cleanup(self):
        """Cleanup after simulation."""
        self.is_running = False
        self.logger.save_to_file()

    def _check_startup_commands(self):
        """Check for startup commands."""

        command = self.proxima_db.db["startup_commands"].find_one_and_delete(
            {"experiment_id": self.exp_id}, sort=[("timestamp", -1)]
        )

        if not command:
            return False

        action = command.get("action")
        print(f"Starting: {action}")

        if action == "start_continuous":
            self.run(continuous=True)
        elif action == "start_limited":
            max_steps = command.get("max_steps", self.sim_time)
            original_sim_time = self.sim_time
            self.sim_time = max_steps
            self.run(continuous=False)
            self.sim_time = original_sim_time

        return True


def main():
    runner = ProximaRunner()

    try:
        while True:
            if not runner.is_running:
                if runner._check_startup_commands():
                    continue
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down...")
        runner.is_running = False


if __name__ == "__main__":
    main()
