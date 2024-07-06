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

from proxima_model.components.lunar_power_grid import LocalMicroGrid
from proxima_model.environments import lunar_env as env
from proxima_model.visualizer import ts_plot as pl


def main():
    print("Proxima - Lunar Power Grid Simulation")

    microgrid_env = simpy.Environment()

    microgrid = LocalMicroGrid(
        microgrid_env,
        num_panels=env.VSAT_NUM,
        load_kwh=env.HABITAT_PWR_CONSUMPTION_RATE_KWH,
        initial_battery_soc=env.BAT_SOC_INI,
    )

    microgrid_env.run(until=env.RUN_TIME_H)
    pl.plot_ts(
        microgrid.generated_power_ts,
        "Generated Power",
        microgrid.load_consumption_ts,
        "Load Consumption",
        "Time (h)",
        "Power (kW)",
        "Power Grid Profile",
    )


if __name__ == "__main__":
    main()
