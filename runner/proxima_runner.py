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

    def run(self, continuous=None):
        """Main simulation runner."""
        continuous = self.sim_time is None if continuous is None else continuous
        
        # Setup and start
        config = build_world_system_config(self.ws_id, self.exp_id, self.proxima_db)
        ws = WorldSystem(config)
        self.is_running = True
        self.is_paused = False

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
                
                # Get state from both sectors
                science_state = ws.science_sector.get_state()
                energy_state = ws.energy_sector.get_state()
                                
                # Get organized metrics from world system
                metrics = ws.model_metrics
                
                # Log with sector organization
                self.logger.log(
                    step=ws.steps,
                    environment=metrics["environment"],
                    energy=metrics["energy"], 
                    science=metrics["science"],
                    latest_state={
                        "step": ws.steps,
                        "microgrid": energy_state,
                        "science_rovers": science_state["science_rovers"],
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
            import traceback
            traceback.print_exc()
        finally:
            self.is_running = False
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
                print(f"Applied: {action}")
                
        except Exception as e:
            print(f"Command error: {e}")


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
