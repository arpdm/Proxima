"""
ProximaRunner: Simulation runner with UI command support.
Supports continuous/limited modes with pause/resume/stop controls.
"""

import time
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

        # Setup logger and control variables
        self.logger = DataLogger(experiment_id=self.exp_id, db=self.proxima_db, ws_id=self.ws_id)
        self.is_running = False
        self.is_paused = False
        self.step_delay = 0.1
        
        self._clear_old_status()

    def _clear_old_status(self):
        """Clear any old simulation status on startup."""
        try:
            ws = self.proxima_db.find_by_id("world_systems", self.ws_id)
            if ws and "simulation_status" in ws.get("latest_state", {}):
                latest_state = ws["latest_state"]
                latest_state["simulation_status"] = {
                    "is_running": False, "is_paused": False, 
                    "step_delay": self.step_delay, "mode": "stopped"
                }
                self.proxima_db.update_document("world_systems", self.ws_id, {"latest_state": latest_state})
                print("Cleared old simulation status")
        except Exception as e:
            print(f"Error clearing status: {e}")

    def run(self, continuous=None):
        """Main simulation runner."""
        continuous = self.sim_time is None if continuous is None else continuous
        
        # Setup and start
        config = build_world_system_config(self.ws_id, self.exp_id, self.proxima_db)
        ws = WorldSystem(config)
        self.is_running = True
        self.is_paused = False
        self._update_status()

        try:
            while self.is_running:
                # Handle pause
                while self.is_paused and self.is_running:
                    time.sleep(0.1)
                    self._check_commands()
                
                if not self.is_running:
                    break

                # Simulation step
                ws.step()
                self.logger.log(
                    step=ws.steps,
                    model_metrics=ws.model_metrics,
                    agent_metrics=[ws.microgrid.agent_state, ws.get_rover_state()],
                    latest_state={
                        "step": ws.steps,
                        "microgrid": ws.microgrid.agent_state,
                        "science_rovers": ws.get_rover_state(),
                        "ws_metrics": ws.model_metrics,
                        "simulation_status": {
                            "is_running": self.is_running,
                            "is_paused": self.is_paused,
                            "step_delay": self.step_delay,
                            "mode": "continuous" if continuous else "limited",
                            "timestamp": time.time()
                        }
                    }
                )

                # Check stop conditions
                if not continuous and self.sim_time and ws.steps >= self.sim_time:
                    break

                self._check_commands()
                time.sleep(self.step_delay)

        except Exception as e:
            print(f"Simulation error: {e}")
        finally:
            self.is_running = False
            self._final_status_update()
            self.logger.save_to_file()

    def _check_commands(self):
        """Process runtime commands."""
        try:
            command = self.proxima_db.db["runtime_commands"].find_one_and_delete(
                {"experiment_id": self.exp_id}, sort=[("timestamp", -1)]
            )
            
            if not command:
                return
                
            action = command.get("action")
            print(f"Processing: {action}")
            
            actions = {
                "pause": lambda: setattr(self, 'is_paused', True),
                "resume": lambda: setattr(self, 'is_paused', False),
                "stop": lambda: setattr(self, 'is_running', False),
                "set_delay": lambda: setattr(self, 'step_delay', max(0.01, float(command.get("delay", 0.1))))
            }
            
            if action in actions:
                actions[action]()
                self._update_status()
                print(f"Applied: {action}")
                
        except Exception as e:
            print(f"Command error: {e}")

    def _update_status(self):
        """Update simulation status via logger."""
        try:
            ws_doc = self.proxima_db.find_by_id("world_systems", self.ws_id)
            if not ws_doc:
                return
                
            current_state = ws_doc.get("latest_state", {})
            updated_state = {
                "step": current_state.get("step", 0),
                "microgrid": current_state.get("microgrid", {}),
                "science_rovers": current_state.get("science_rovers", []),
                "ws_metrics": current_state.get("ws_metrics", {}),
                "simulation_status": {
                    "is_running": self.is_running,
                    "is_paused": self.is_paused,
                    "step_delay": self.step_delay,
                    "mode": "continuous",
                    "timestamp": time.time()
                }
            }
            
            self.logger.log(
                step=current_state.get("step", 0),
                model_metrics=current_state.get("ws_metrics", {}),
                agent_metrics=[current_state.get("microgrid", {}), current_state.get("science_rovers", [])],
                latest_state=updated_state
            )
            print(f"Status: running={self.is_running}, paused={self.is_paused}")
            
        except Exception as e:
            print(f"Status update error: {e}")

    def _final_status_update(self):
        """Set final stopped status."""
        try:
            ws_doc = self.proxima_db.find_by_id("world_systems", self.ws_id)
            if ws_doc:
                current_state = ws_doc.get("latest_state", {})
                final_state = {
                    "step": current_state.get("step", 0),
                    "microgrid": current_state.get("microgrid", {}),
                    "science_rovers": current_state.get("science_rovers", []),
                    "ws_metrics": current_state.get("ws_metrics", {}),
                    "simulation_status": {
                        "is_running": False, "is_paused": False,
                        "step_delay": self.step_delay, "mode": "stopped", "timestamp": time.time()
                    }
                }
                
                self.logger.log(
                    step=current_state.get("step", 0),
                    model_metrics=current_state.get("ws_metrics", {}),
                    agent_metrics=[current_state.get("microgrid", {}), current_state.get("science_rovers", [])],
                    latest_state=final_state
                )
                print("Final status: STOPPED")
        except Exception as e:
            print(f"Final status error: {e}")


def main():
    runner = ProximaRunner()
    print("Proxima Runner ready. Waiting for UI commands...")
    
    try:
        while True:
            if not runner.is_running:
                command = runner.proxima_db.db["startup_commands"].find_one_and_delete(
                    {"experiment_id": runner.exp_id}, sort=[("timestamp", -1)]
                )
                
                if command:
                    action = command.get("action")
                    print(f"Starting: {action}")
                    
                    if action == "start_continuous":
                        runner.run(continuous=True)
                    elif action == "start_limited":
                        max_steps = command.get("max_steps", runner.sim_time)
                        original_sim_time = runner.sim_time
                        runner.sim_time = max_steps
                        runner.run(continuous=False)
                        runner.sim_time = original_sim_time
                        
                    print("Simulation completed. Waiting...")
                    
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nShutting down...")
        runner.is_running = False


if __name__ == "__main__":
    main()
