"""
proxima_runner.py

This script initializes and runs a simulation for the Proxima project.
It sets up the database, loads experiment configuration, builds the world system,
and steps through the simulation for the specified number of time steps.
"""

from data_engine.proxima_db_engine import ProximaDB
from proxima_model.world_system_builder.world_system_builder import build_world_system_config
from proxima_model.world_system_builder.world_system import WorldSystem
from proxima_model.tools.data_logger import DataLogger


class ProximaRunner:
    def __init__(self):
        # Setup Simulation
        self.proxima_db = ProximaDB()
        # Deletes all documents in the logs_simulation collection
        self.proxima_db.db.db.logs_simulation.delete_many({})

        # Setup World System Config
        experiment_config = self.proxima_db.find_by_id("experiments", "exp_001")
        self.sim_time = experiment_config["simulation_time_stapes"]
        self.ws_id = experiment_config["world_system_id"]
        self.exp_id = experiment_config["_id"]

        # Setup Data Logger
        self.logger = DataLogger(experiment_id=self.exp_id, db=self.proxima_db, ws_id=self.ws_id)

    def run(self):
        """
        Main entry point for running a Proxima simulation.
        - Initializes the database connection.
        - Loads experiment configuration from the database.
        - Builds the world system using the configuration.
        - Runs the simulation for the configured number of time steps.
        """
        # Configure and build world system
        config = build_world_system_config(self.ws_id, self.exp_id, self.proxima_db)
        ws = WorldSystem(config)
        
        # Run Simulation
        for _ in range(self.sim_time):
            ws.step()
            latest_state = {
                "step": ws.steps,
                "microgrid": ws.microgrid.agent_state,
                "science_rovers": ws.get_rover_state(),
                "ws_metrics": ws.model_metrics,
                # add other agent/system states as needed
            }

            self.logger.log(
                step=ws.steps,
                model_metrics=ws.model_metrics,
                agent_metrics=[ws.microgrid.agent_state, ws.get_rover_state()],
                latest_state=latest_state,
            )

        self.logger.save_to_file()


def main():
    proxima_runner = ProximaRunner()
    proxima_runner.run()


if __name__ == "__main__":
    main()
