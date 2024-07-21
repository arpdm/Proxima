"""
lunar_power_grid_simulation.py
==============================

Description:
    This is the main entry point for running the Proxima - Lunar Power Grid Simulation.
    The simulation uses the SimPy library to model the operation of a lunar microgrid
    that includes solar panels (VSATs) and a battery storage system. The results are 
    plotted using Matplotlib to visualize power generation and load consumption over time.

Author:
    Arpi Derm <arpiderm@gmail.com>

Created:
    July 5, 2024

Dependencies:
    - simpy: Discrete event simulation for Python (https://simpy.readthedocs.io/)
    - matplotlib: Plotting library for Python (https://matplotlib.org/)
    - proxima_model.components.lunar_power_grid: Contains the LocalMicroGrid class for the simulation
    - proxima_model.environments.lunar_env: Provides environment variables specific to the lunar simulation

Usage:
    To run the simulation, execute this script using poetry
        poetry run lunar-power-grid

License:
    MIT License

Functions:
    - main: The main function to set up and run the lunar power grid simulation.

"""

import simpy

from proxima_model.components.local_microgrid import LocalMicroGrid
from proxima_model.environments import lunar_env as env
from proxima_model.visualizer import ts_plot as pl
from proxima_model.tools.logger import Logger
from pathlib import Path


def get_log_file_directory():
    """Preps the log file directory and returns the path for it.

    Returns:
        Path: Path for log_files directory
    """
    script_path = Path(__file__).resolve()
    log_dir = script_path.parent.parent.parent / "log_files"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def main():

    # Setup
    logger = Logger()
    logger.set_file(get_log_file_directory() / "output_log.txt")
    logger.enable()

    # Simulation Environment
    microgrid_env = simpy.Environment()
    microgrid = LocalMicroGrid(
        microgrid_env,
        num_panels=env.VSAT_NUM,
        load_kwh=(env.HABITAT_PWR_CONSUMPTION_RATE_KWH * env.HABITAT_NUM),
        initial_battery_soc=env.BAT_SOC_INI,
        num_batteries=env.BATTERY_NUM,
    )

    microgrid_env.run(until=env.RUN_TIME_H)

    # Post Processing
    microgrid.save_data(get_log_file_directory() / "lunar_microgrid_sim_001.csv")
    pl.plot_time_series_multi_feature(microgrid.data_drame, "time_h", "Lunar Microgrid System State")
    pl.plot_time_series_multi_feature(microgrid.batteries_soc_df, "time_h", "Lunar Microgrid Batteries SoC")

    # Cleanup
    logger.reset()


if __name__ == "__main__":
    main()
