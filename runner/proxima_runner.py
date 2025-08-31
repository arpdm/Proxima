"""
ProximaRunner: Simplified simulation runner with UI command support.
"""

import time
import traceback
import argparse

from data_engine.proxima_db_engine import ProximaDB
from proxima_model.world_system_builder.world_system_builder import build_world_system_config
from proxima_model.world_system_builder.world_system import WorldSystem
from proxima_model.tools.data_logger import DataLogger

# ==== DEF ====

HOST_UPDATED_FREQUENCY = 600  # How often to update the hosted DB with simulation state

def parse_args():
    """Parse command-line arguments for runner options."""
    parser = argparse.ArgumentParser(description="Proxima Simulation Runner")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (no UI commands)")
    parser.add_argument("--mongo-uri", type=str, default=None, help="MongoDB URI (overrides db choice)")
    return parser.parse_args()

class ProximaRunner:
    """Main simulation runner class for Proxima."""

    def __init__(self, mongo_uri=None):
        # Setup database connections
        if mongo_uri:
            hosted_uri = mongo_uri
        else:  # Local
            hosted_uri = None
        
        self.local_uri = "mongodb://localhost:27017"
        self.proxima_db = ProximaDB(uri=self.local_uri)
        self.proxima_hosted_db = ProximaDB(uri=hosted_uri) if hosted_uri else None
        self.proxima_db.db.db.logs_simulation.delete_many({})  # Clear old logs

        # Load experiment configuration from DB
        exp_config = self.proxima_db.find_by_id("experiments", "exp_001")
        self.sim_time = exp_config.get("simulation_time_stapes", None)
        self.ws_id = exp_config["world_system_id"]
        self.exp_id = exp_config["_id"]

        # Setup logging and simulation state
        self.logger = DataLogger(experiment_id=self.exp_id, db=self.proxima_db, ws_id=self.ws_id)
        self.hosted_logger = DataLogger(experiment_id=self.exp_id, db=self.proxima_hosted_db, ws_id=self.ws_id)
        self.is_running = False
        self.is_paused = False
        self.continuous = True
        self.ws = None
        self.step_delay = 0.1
        self.host_update_frequency = HOST_UPDATED_FREQUENCY

    def run(self, continuous=None):
        """Main simulation runner loop."""
        self.continuous = continuous if continuous is not None else (self.sim_time is None)

        # Build world system configuration and initialize WorldSystem
        config = build_world_system_config(self.ws_id, self.exp_id, self.proxima_db)
        self.ws = WorldSystem(config, 100)
        self.is_running = True
        self.is_paused = False
        update_counter = 0 # Counter to know when to update the hosted server with state of the world system

        try:
            while self.is_running and (continuous or self.ws.steps < self.sim_time):
                self._process_commands()  # Check for runtime commands (pause, resume, etc.)

                if self.is_paused:
                    time.sleep(0.1)
                    continue
                if not self.is_running:
                    #TODO: File logger needs to be more efficient. We need to save to file in chuncks and clear the cache to not hug memory
                    self.logger.save_to_file()
                    break

                # Step the world system and update the state
                self.ws.step()
                update_counter += 1
                update_hosted = (self.proxima_hosted_db and (update_counter >= self.host_update_frequency))
                self._update_world_system_state(update_hosted=update_hosted)
                if update_hosted:
                    update_counter = 0
                time.sleep(self.step_delay)

        except Exception as e:
            print(f"Simulation error: {e}")
            traceback.print_exc()
        finally:
            self.is_running = False
            self.is_paused = False
            self._update_world_system_state()

    def _process_commands(self):
        """Process runtime commands from the database (pause, resume, stop, set_delay)."""
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

        # Build current state snapshot
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

        # Log metrics and state to local DB
        self.logger.log(
            step= self.ws.steps,
            environment= self.ws.model_metrics["environment"],
            energy= self.ws.model_metrics["energy"],
            science= self.ws.model_metrics["science"],
            manufacturing= self.ws.model_metrics["manufacturing"],
            performance= self.ws.model_metrics.get("performance", {}),
            latest_state=self.current_state,
        )

        # Optionally update hosted DB for remote UI
        if update_hosted:
            self.hosted_logger.log(
                step=self.ws.steps,
                environment=self.ws.model_metrics["environment"],
                energy=self.ws.model_metrics["energy"],
                science=self.ws.model_metrics["science"],
                manufacturing=self.ws.model_metrics["manufacturing"],
                performance=self.ws.model_metrics.get("performance", {}),
                latest_state=self.current_state,
            )

    def _check_startup_commands(self):
        """Check for startup commands in the database and start simulation accordingly."""

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
    """Entry point for Proxima simulation runner."""

    args = parse_args()

    # If Mongo DB Server URL is not provided, the model will not sync its state to the server only to local database.
    if args.mongo_uri:
        mongo_uri = args.mongo_uri
    else:
        mongo_uri = None

    runner = ProximaRunner(mongo_uri=mongo_uri)

    try:
        if args.headless:
            print("Running Proxima in Headless Mode")
            runner.run(continuous=True)
        else:
            # UI mode: wait for startup commands to begin simulation
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
