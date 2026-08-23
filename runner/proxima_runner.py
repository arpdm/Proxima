"""
ProximaRunner: Simplified simulation runner with UI command support.
"""

import time
import traceback
import argparse
import logging
import os

from dataclasses import dataclass

from data_engine.proxima_db_engine import ProximaDB
from proxima_model.world_system.world_system_builder import build_world_system_config
from proxima_model.world_system.world_system import WorldSystem
from proxima_model.tools.data_logger import DataLogger
from proxima_model.world_system.world_system_defs import get_sector_list, RunnerConfig


# ==== CONFIG ====

logging.basicConfig(
    level=logging.WARNING,  # Set default level
    format="%(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],  # Output to console
)

debug_logger = logging.getLogger(__name__)
debug_logger.setLevel(logging.INFO)

logging.getLogger("proxima_model.sphere_engine.transportation_sector").setLevel(logging.ERROR)
logging.getLogger("proxima_model.sphere_engine.science_sector").setLevel(logging.ERROR)
logging.getLogger("proxima_model.sphere_engine.manufacturing_sector").setLevel(logging.ERROR)
logging.getLogger("proxima_model.policy_engine.policy_engine").setLevel(logging.ERROR)
logging.getLogger("proxima_model.policy_engine.science_policies").setLevel(logging.ERROR)
logging.getLogger("proxima_model.world_system.world_system").setLevel(logging.ERROR)
logging.getLogger("proxima_model.sphere_engine.construction_sector").setLevel(logging.INFO)
logging.getLogger("proxima_model.sphere_engine.equipment_manufacturing_sector").setLevel(logging.ERROR)
logging.getLogger("proxima_model.world_system.evaluation_engine").setLevel(logging.ERROR)
logging.getLogger("proxima_model.components.science_rover").setLevel(logging.ERROR)
logging.getLogger("proxima_model.components.rocket").setLevel(logging.ERROR)
logging.getLogger("proxima_model.components.assembly_robot").setLevel(logging.ERROR)


def parse_args():
    """Parse command-line arguments for runner options."""

    parser = argparse.ArgumentParser(description="Proxima Simulation Runner")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (no UI commands)")
    parser.add_argument("--mongo-uri", type=str, default=None, help="MongoDB URI (overrides db choice)")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["live", "test"],
        default="live",
        help=(
            "Run mode. 'live' (default) resumes prior world system state and sol/step count, "
            "and periodically saves data to hosted_uri. 'test' never saves to hosted_uri and "
            "always starts from a reset sol/step count and a reset world system state."
        ),
    )
    return parser.parse_args()


# ==== CONFIG END ====


@dataclass()
class ExperimentConfig:
    """Resolved experiment configuration for a run."""

    sim_time: int | None
    ws_id: str
    time_scale_h_per_step: float
    exp_id: str


class ProximaRunner:
    """Main simulation runner class for Proxima."""

    def __init__(self, mongo_uri=None, config: RunnerConfig = None):
        self.config = config or RunnerConfig()
        if mongo_uri:
            self.config.hosted_uri = mongo_uri

        self.run_mode = (self.config.run_mode or "live").lower()
        if self.run_mode not in ("live", "test"):
            raise ValueError(f"Invalid run_mode: {self.run_mode!r}. Must be 'live' or 'test'.")
        self.is_test_mode = self.run_mode == "test"

        # Setup database connections. In test mode we never talk to the hosted DB:
        # nothing gets saved to hosted_uri regardless of what was configured.
        self.local_db = ProximaDB(uri=self.config.local_uri)
        self.hosted_db = (
            ProximaDB(uri=self.config.hosted_uri, local=False)
            if (self.config.hosted_uri and not self.is_test_mode)
            else None
        )

        # Fail loudly and immediately at startup rather than silently swallowing every
        # subsequent write - otherwise a bad/missing hosted_uri or unreachable Atlas
        # cluster looks identical to "everything's fine, just not saving."
        if not self.is_test_mode:
            if not self.config.hosted_uri:
                debug_logger.warning(
                    "⚠️ No hosted_uri configured - nothing will be saved to the hosted DB. "
                    "Pass --mongo-uri <atlas-connection-string> to enable it."
                )
            elif self.hosted_db is not None:
                try:
                    self.hosted_db.client.admin.command("ping")
                    debug_logger.info(f"✅ Connected to hosted MongoDB at {self.config.hosted_uri}")
                except Exception as e:
                    debug_logger.error(f"❌ Could not connect to hosted MongoDB ({self.config.hosted_uri}): {e}")
                    self.hosted_db = None

        self.local_db.db["logs_simulation"].delete_many({})  # Clear old logs

        # Load experiment configuration from DB
        self.experiment = self._load_experiment_config()

        # Clear any stale commands left over from a previous session for this experiment.
        # Without this, a leftover "stop"/"pause" command can be replayed the moment the
        # simulation starts, immediately halting it again.
        self.local_db.db["startup_commands"].delete_many({"experiment_id": self.experiment.exp_id})
        self.local_db.db["runtime_commands"].delete_many({"experiment_id": self.experiment.exp_id})

        # In test mode, reset the world system's persisted state so the run always
        # starts fresh (no resumed sector state, no resumed sol/step count).
        if self.is_test_mode:
            self._reset_world_system_state()

        # Setup logging and simulation state
        self.logger = DataLogger(experiment_id=self.experiment.exp_id, db=self.local_db, ws_id=self.experiment.ws_id)

        self.hosted_logger = (
            DataLogger(experiment_id=self.experiment.exp_id, db=self.hosted_db, ws_id=self.experiment.ws_id)
            if self.hosted_db
            else None
        )

        self.is_running = False
        self.is_paused = False
        self.continuous = True
        self.ws = None
        self.step_delay = self.config.default_step_delay
        self.step_counter = 0  # For periodic tasks like log flushing
        self.monte_carlo_context = None

    def _load_experiment_config(self) -> ExperimentConfig:
        """Load experiment configuration from the database."""

        exp_config = self.local_db.find_by_id("experiments", self.config.experiment)
        return ExperimentConfig(
            sim_time=exp_config.get("simulation_time_steps", None),
            ws_id=exp_config["world_system_id"],
            time_scale_h_per_step=exp_config["hours_per_time_step"],
            exp_id=exp_config["_id"],
        )

    def _reset_world_system_state(self) -> None:
        """Clear the world system's persisted latest_state (test mode only)."""

        self.local_db.db["world_systems"].update_one(
            {"_id": self.experiment.ws_id},
            {"$unset": {"latest_state": ""}},
        )

    def _build_world_system(self) -> WorldSystem:
        """Create a world system instance for the current experiment."""

        # Live runs resume prior sector state and continue the sol/step count;
        # test runs always start clean with a reset sol/step count of 0.
        resume_state = not self.is_test_mode
        config = build_world_system_config(
            self.experiment.ws_id, self.experiment.exp_id, self.local_db, resume_state=resume_state
        )
        
        ws = WorldSystem(config, 100)

        if resume_state:
            world_system = self.local_db.find_by_id("world_systems", self.experiment.ws_id)
            resumed_step = (world_system or {}).get("latest_state", {}).get("step")
            if isinstance(resumed_step, int) and resumed_step > 0:
                ws.steps = resumed_step

        return ws

    def run(self, continuous=None):
        """Main simulation runner loop."""

        self.continuous = continuous if continuous is not None else (self.experiment.sim_time is None)
        self.ws = self._build_world_system()
        self.is_running = True
        self.is_paused = False
        update_counter = 0

        # "Limited" runs (Start Limited / Monte Carlo) mean "run N more steps from here",
        # not "run until absolute step N" - otherwise resuming a live run whose step count
        # already exceeds a previously-used Max Steps value would execute zero steps.
        self._step_limit = None if self.continuous else self.ws.steps + self.experiment.sim_time

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
                update_counter = self._handle_post_step_tasks(update_counter)
                time.sleep(self.step_delay)

        except Exception as e:
            debug_logger.error(f"Simulation error: {e}")
            traceback.print_exc()
        finally:
            self._finalize_run()

    def _should_continue(self):
        """Check if the simulation should continue."""
        return self.is_running and (self.continuous or self.ws.steps < self._step_limit)

    def _perform_simulation_step(self):
        """Perform a single simulation step."""

        self.ws.step()
        self.step_counter += 1

    def _handle_post_step_tasks(self, update_counter: int) -> int:
        """Handle tasks after each step, like logging and updates."""

        update_hosted = self.hosted_db and (update_counter >= self.config.host_update_frequency)
        self._update_world_system_state(update_hosted=update_hosted)

        # Only used for updated the online hosted database
        if update_hosted:
            update_counter = 0
        else:
            update_counter += 1

        # Periodic log flushing to manage memory
        if self.step_counter % self.config.log_flush_interval == 0:
            self.logger.save_to_file()

        return update_counter

    def _finalize_run(self):
        """Finalize the run by saving logs and resetting state."""

        self.logger.save_to_file()

        if self.hosted_logger:
            self.hosted_logger.save_to_file()

        self.is_running = False
        self.is_paused = False
        # Force a hosted push on finalize - otherwise a run that stops/restarts before
        # update_counter reaches host_update_frequency never writes to the hosted DB at all.
        self._update_world_system_state(update_hosted=bool(self.hosted_db))

    def _process_commands(self):
        """Process all pending runtime commands from the database (pause, resume, stop, set_delay).

        Drains every queued command in timestamp order rather than just the latest one -
        otherwise commands issued between two polls (e.g. rapid step-delay edits) get
        silently deleted without ever being applied.
        """

        try:
            commands = list(
                self.local_db.db["runtime_commands"]
                .find({"experiment_id": self.experiment.exp_id})
                .sort("timestamp", 1)
            )
            if not commands:
                return

            self.local_db.db["runtime_commands"].delete_many({"_id": {"$in": [c["_id"] for c in commands]}})
            for command in commands:
                self._execute_command(command)
        except Exception as e:
            debug_logger.error(f"Command processing error: {e}")

    def _execute_command(self, command):
        """Execute a single runtime command that directly changes simulation state."""

        action = command.get("action")
        debug_logger.info(f"Processing: {action}")

        command_map = {
            "pause": lambda: setattr(self, "is_paused", True),
            "resume": lambda: setattr(self, "is_paused", False),
            "stop": lambda: setattr(self, "is_running", False),
            "set_delay": lambda: self._set_step_delay(command),
        }

        if action in command_map:
            command_map[action]()
            debug_logger.info(f"Applied: {action}")

    def _set_step_delay(self, command, *, warn_missing: bool = True) -> None:
        """Apply a step-delay command without falling back to an unrelated default."""

        delay = command.get("delay", command.get("step_delay", None))
        if delay is None:
            if warn_missing:
                debug_logger.warning("Ignoring set_delay command with no delay value")
            return

        try:
            self.step_delay = max(0.01, float(delay))
            debug_logger.info(f"Step delay set to {self.step_delay}")
        except (TypeError, ValueError):
            debug_logger.warning(f"Ignoring invalid step delay value: {delay!r}")

    def _apply_pending_step_delay_commands(self) -> None:
        """Apply queued delay edits made before the simulation starts."""

        delay_commands = list(
            self.local_db.db["runtime_commands"]
            .find({"experiment_id": self.experiment.exp_id, "action": "set_delay"})
            .sort("timestamp", 1)
        )
        if not delay_commands:
            return

        self.local_db.db["runtime_commands"].delete_many({"_id": {"$in": [c["_id"] for c in delay_commands]}})
        for command in delay_commands:
            self._set_step_delay(command)

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

        # 🎯 Build metrics dict with only what exists
        metrics_to_log = {
            "step": self.ws.steps,
            "latest_state": self.current_state,
        }

        if self.monte_carlo_context:
            metrics_to_log.update(self.monte_carlo_context)

        # Add all available sector metrics
        for sector_name in get_sector_list():
            if sector_name in self.ws.model_metrics:
                metrics_to_log[sector_name] = self.ws.model_metrics[sector_name]
            else:
                debug_logger.warning(f"⚠️ Warning: {sector_name} metrics not found, skipping")

        # Log to local DB
        self.logger.log(**metrics_to_log)

        # Optionally update hosted DB
        if update_hosted and self.hosted_logger:
            self.hosted_logger.log(**metrics_to_log)

    def _check_startup_commands(self):
        """Check for startup commands in the database and start simulation accordingly."""

        try:
            command = self.local_db.db["startup_commands"].find_one_and_delete(
                {"experiment_id": self.experiment.exp_id}, sort=[("timestamp", -1)]
            )

            if not command:
                return False

            action = command.get("action")
            debug_logger.info(f"Starting: {action}")
            debug_logger.info(f"Startup command payload: {command}")

            if action == "start_continuous":
                self._apply_pending_step_delay_commands()
                self._set_step_delay(command, warn_missing=False)
                self.logger.clear_display_logs()
                self.run(continuous=True)
            elif action == "start_limited":
                self._apply_pending_step_delay_commands()
                self._set_step_delay(command, warn_missing=False)
                self.logger.clear_display_logs()
                max_steps = command.get("max_steps", self.experiment.sim_time)
                original_sim_time = self.experiment.sim_time
                self.experiment.sim_time = max_steps
                self.run(continuous=False)
                self.experiment.sim_time = original_sim_time
            elif action == "start_monte_carlo":
                self._apply_pending_step_delay_commands()
                self._set_step_delay(command, warn_missing=False)
                steps_per_run = int(command.get("steps_per_run", self.experiment.sim_time or 1))
                num_runs = int(command.get("num_runs", 1))
                self.run_monte_carlo(steps_per_run=steps_per_run, num_runs=num_runs)
            return True
        except Exception as e:
            debug_logger.error(f"Startup command error: {e}")
            return False

    def run_monte_carlo(self, steps_per_run: int, num_runs: int) -> None:
        """Run multiple independent simulations and tag logs with Monte Carlo metadata."""

        if steps_per_run < 1 or num_runs < 1:
            debug_logger.error("Monte Carlo parameters must be >= 1")
            return

        mc_session_id = f"mc_{int(time.time())}"
        original_sim_time = self.experiment.sim_time
        original_log_dir = self.logger.get_config().log_dir

        for run_index in range(1, num_runs + 1):
            mc_run_id = f"{mc_session_id}_run_{run_index:03d}"
            log_dir = os.path.join(
                "log_files",
                "monte_carlo",
                self.experiment.exp_id,
                mc_session_id,
            )

            self.monte_carlo_context = {
                "monte_carlo_session_id": mc_session_id,
                "monte_carlo_run_id": mc_run_id,
                "monte_carlo_run_index": run_index,
                "monte_carlo_steps_per_run": steps_per_run,
            }

            self.logger.rotate_log_dir(log_dir)

            self.experiment.sim_time = steps_per_run
            self.run(continuous=False)

        self.monte_carlo_context = None
        self.logger.rotate_log_dir(original_log_dir)
        self.experiment.sim_time = original_sim_time


def main():
    """Entry point for Proxima simulation runner."""
    args = parse_args()
    config = RunnerConfig(hosted_uri=args.mongo_uri, run_mode=args.mode)
    runner = ProximaRunner(config=config)

    try:
        if args.headless:
            debug_logger.info("Running Proxima in Headless Mode")
            runner.run(continuous=True)
        else:
            # UI mode: wait for startup commands
            while True:
                if not runner.is_running:
                    if runner._check_startup_commands():
                        continue
                time.sleep(1)
    except KeyboardInterrupt:
        debug_logger.info("\nShutting down...")
        runner.is_running = False


if __name__ == "__main__":
    main()
