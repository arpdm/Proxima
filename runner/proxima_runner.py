"""
ProximaRunner: Simplified simulation runner with UI command support.
"""

import time
import traceback
import argparse
import logging

from dataclasses import dataclass

from data_engine.proxima_db_engine import ProximaDB
from proxima_model.world_system_builder.world_system_builder import build_world_system_config
from proxima_model.world_system_builder.world_system import WorldSystem
from proxima_model.tools.data_logger import DataLogger

# ==== CONFIG ====
@dataclass
class RunnerConfig:
    """Configuration for the ProximaRunner."""

    local_uri: str = "mongodb://localhost:27017"
    hosted_uri: str = None
    host_update_frequency: int = 600
    default_step_delay: float = 0.1
    log_flush_interval: int = 1000  # Flush logs every N steps to manage memory

def parse_args():
    """Parse command-line arguments for runner options."""
    
    parser = argparse.ArgumentParser(description="Proxima Simulation Runner")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (no UI commands)")
    parser.add_argument("--mongo-uri", type=str, default=None, help="MongoDB URI (overrides db choice)")
    return parser.parse_args()

class ProximaRunner:
    """Main simulation runner class for Proxima."""

    def __init__(self, mongo_uri=None, config: RunnerConfig = None):
        self.config = config or RunnerConfig()
        if mongo_uri:
            self.config.hosted_uri = mongo_uri
        
        # Setup database connections
        self.local_db = ProximaDB(uri=self.config.local_uri)
        self.hosted_db = ProximaDB(uri=self.config.hosted_uri) if self.config.hosted_uri else None
        self.local_db.db.db.logs_simulation.delete_many({})  # Clear old logs

        # Load experiment configuration from DB
        exp_config = self.local_db.find_by_id("experiments", "exp_001")
        self.sim_time = exp_config.get("simulation_time_stapes", None)
        self.ws_id = exp_config["world_system_id"]
        self.exp_id = exp_config["_id"]

        # Setup logging and simulation state
        self.logger = DataLogger(experiment_id=self.exp_id, db=self.local_db, ws_id=self.ws_id)
        self.hosted_logger = DataLogger(experiment_id=self.exp_id, db=self.hosted_db, ws_id=self.ws_id) if self.hosted_db else None
        self.is_running = False
        self.is_paused = False
        self.continuous = True
        self.ws = None
        self.step_delay = self.config.default_step_delay
        self.step_counter = 0  # For periodic tasks like log flushing

    def run(self, continuous=None):
        """Main simulation runner loop."""

        self.continuous = continuous if continuous is not None else (self.sim_time is None)
        config = build_world_system_config(self.ws_id, self.exp_id, self.local_db)
        self.ws = WorldSystem(config, 100)
        self.is_running = True
        self.is_paused = False
        update_counter = 0

        try:
            while self._should_continue():

                self._process_commands()

                if self.is_paused:
                    time.sleep(0.1)
                    continue
                if not self.is_running:
                    self._finalize_run()
                    break

                # Break into smaller methods ---
                self._perform_simulation_step()
                self._handle_post_step_tasks(update_counter)
                update_counter += 1
                time.sleep(self.step_delay)

        except Exception as e:
            print(f"Simulation error: {e}")
            traceback.print_exc()
        finally:
            self._finalize_run()

    def _should_continue(self):
        """Check if the simulation should continue."""
        return self.is_running and (self.continuous or self.ws.steps < self.sim_time)

    def _perform_simulation_step(self):
        """Perform a single simulation step."""

        self.ws.step()
        self.step_counter += 1

    def _handle_post_step_tasks(self, update_counter):
        """Handle tasks after each step, like logging and updates."""

        update_hosted = self.hosted_db and (update_counter >= self.config.host_update_frequency)
        self._update_world_system_state(update_hosted=update_hosted)

        # Only used for updated the online hosted database
        if update_hosted:
            update_counter = 0
        
        # Periodic log flushing to manage memory
        if self.step_counter % self.config.log_flush_interval == 0:
            self.logger.save_to_file()

    def _finalize_run(self):
        """Finalize the run by saving logs and resetting state."""

        self.logger.save_to_file()

        if self.hosted_logger:
            self.hosted_logger.save_to_file()

        self.is_running = False
        self.is_paused = False
        self._update_world_system_state()

    def _process_commands(self):
        """Process runtime commands from the database (pause, resume, stop, set_delay)."""

        try:
            command = self.local_db.db["runtime_commands"].find_one_and_delete(
                {"experiment_id": self.exp_id}, sort=[("timestamp", -1)]
            )
            if command:
                self._execute_command(command)
        except Exception as e:
            print(f"Command processing error: {e}")

    def _execute_command(self, command):
        """Execute a single runtime command."""

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

    def _update_world_system_state(self, update_hosted=False):
        """Update world system state in MongoDB for UI access and logging."""

        self.current_state = {
            "step": self.ws.steps,
            "simulation_status": {
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "step_delay": self.step_delay,
                "mode": "continuous" if self.continuous else "limited",
                "timestamp": time.time(),
            },
        }

        # Log to local DB
        self.logger.log(
            step=self.ws.steps,
            environment=self.ws.model_metrics["environment"],
            energy=self.ws.model_metrics["energy"],
            science=self.ws.model_metrics["science"],
            manufacturing=self.ws.model_metrics["manufacturing"],
            equipment_manufacturing=self.ws.model_metrics["equipment_manufacturing"],
            transportation=self.ws.model_metrics["transportation"],
            performance=self.ws.model_metrics.get("performance", {}),
            latest_state=self.current_state,
        )

        # Optionally update hosted DB
        if update_hosted and self.hosted_logger:
            self.hosted_logger.log(
                step=self.ws.steps,
                environment=self.ws.model_metrics["environment"],
                energy=self.ws.model_metrics["energy"],
                science=self.ws.model_metrics["science"],
                manufacturing=self.ws.model_metrics["manufacturing"],
                equipment_manufacturing=self.ws.model_metrics["equipment_manufacturing"],
                transportation=self.ws.model_metrics["transportation"],
                performance=self.ws.model_metrics.get("performance", {}),
                latest_state=self.current_state,
            )

    def _check_startup_commands(self):
        """Check for startup commands in the database and start simulation accordingly."""

        try:
            command = self.local_db.db["startup_commands"].find_one_and_delete(
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
        except Exception as e:
            print(f"Startup command error: {e}")
            return False

def main():
    """Entry point for Proxima simulation runner."""
    args = parse_args()
    config = RunnerConfig(hosted_uri=args.mongo_uri)
    runner = ProximaRunner(config=config)

    try:
        if args.headless:
            print("Running Proxima in Headless Mode")
            runner.run(continuous=True)
        else:
            # UI mode: wait for startup commands
            while True:
                if not runner.is_running:
                    if runner._check_startup_commands():
                        continue
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        runner.is_running = False

if __name__ == "__main__":
    
    # Configure Logging
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('proxima_model.components.rocket').setLevel(logging.INFO)
    logging.getLogger('proxima_model.components.isru').setLevel(logging.ERROR)
    logging.getLogger('proxima_model.sphere_engine.equipment_manufacturing_sector').setLevel(logging.ERROR)
    logging.getLogger('proxima_model.sphere_engine.manufacturing_sector').setLevel(logging.ERROR)
    logging.getLogger('proxima_model.sphere_engine.science_sector').setLevel(logging.ERROR)
    logging.getLogger('proxima_model.sphere_engine.transportation_sector').setLevel(logging.ERROR)
    logging.getLogger('proxima_model.world_system_builder.world_system_builder').setLevel(logging.ERROR)
    logging.getLogger('proxima_model.world_system_builder.world_system').setLevel(logging.ERROR)
    logging.getLogger('proxima_model.tools.data_logger').setLevel(logging.ERROR)
    main()
