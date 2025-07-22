"""
proxima_runner.py

This script initializes and runs a simulation for the Proxima project.
It sets up the database, loads experiment configuration, builds the world system,
and steps through the simulation for the specified number of time steps.
"""

from datetime import datetime, timezone
from data_engine.proxima_db_engine import ProximaDB
from proxima_model.world_system_builder.world_system_builder import build_world_system_config
from proxima_model.world_system_builder.world_system import WorldSystem
from proxima_model.tools.data_logger import DataLogger


def main():
    """
    Main entry point for running a Proxima simulation.
    - Initializes the database connection.
    - Loads experiment configuration from the database.
    - Builds the world system using the configuration.
    - Runs the simulation for the configured number of time steps.
    """
    # Setup Simulation
    start_time = datetime.now(timezone.utc).timestamp()
    proxima_db = ProximaDB()

    experiment_config = proxima_db.find_by_id("experiments", "exp_001")
    sim_time = experiment_config["simulation_time_stapes"]
    ws_id = experiment_config["world_system_id"]
    exp_id = experiment_config["_id"]

    # Setup Data Logger
    logger = DataLogger(experiment_id=exp_id, db=proxima_db)

    # Configure and build world system
    config = build_world_system_config(ws_id, exp_id, proxima_db)
    print(f"World System Config: {config}")
    ws = WorldSystem(config)

    # Run Simulation
    for _ in range(sim_time):
        ws.step()
        logger.log(ws.steps, ws.model_metrics, [ws.microgrid.agent_state])

    logger.save_to_file()

    # Close db client session
    #proxima_db.client.close()


if __name__ == "__main__":
    main()
