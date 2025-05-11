"""
lunar_power_grid_simulation.py
==============================

Description:
    This is the main entry point for running the Proxima - World System Beta Phase 1

Author:
    Arpi Derm <arpiderm@gmail.com>

Created:
    July 5, 2024

Usage:
    To run the simulation, execute this script using poetry
        poetry run lunar-power-grid

License:
    MIT License

Functions:
    - main: The main function to set up and run the lunar power grid simulation.

"""

from proxima_model.tools import ts_plot as pl
from proxima_model.tools.logger import Logger
from pathlib import Path

import matplotlib.pyplot as plt  # You need to import this too
import numpy as np
import pandas as pd
import seaborn as sns
import mesa

from mesa.experimental.cell_space import CellAgent, OrthogonalMooreGrid

def get_log_file_directory():
    """Preps the log file directory and returns the path for it.

    Returns:
        Path: Path for log_files directory
    """
    script_path = Path(__file__).resolve()
    log_dir = script_path.parent.parent.parent / "log_files"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir

def compute_gini(model):
    agent_wealths = [agent.wealth for agent in model.agents]
    x = sorted(agent_wealths)
    n = model.num_agents
    B = sum(xi * (n - i) for i, xi in enumerate(x)) / (n * sum(x))
    return 1 + (1 / n) - 2 * B


class MoneyAgent(CellAgent):
    """An agent with fixed initial wealth."""

    def __init__(self, model, cell):
        super().__init__(model)
        self.cell = cell
        self.wealth = 1
        self.steps_not_given = 0

    def move(self):
        self.cell = self.cell.neighborhood.select_random_cell()

    def give_money(self):
        cellmates = [a for a in self.cell.agents if a is not self]

        if len(cellmates) > 0 and self.wealth > 0:
            other = self.random.choice(cellmates)
            other.wealth += 1
            self.wealth -= 1
            self.steps_not_given = 0
        else:
            self.steps_not_given += 1


class MoneyModel(mesa.Model):
    """A model with some number of agents."""

    def __init__(self, n, width, height, seed=None):
        super().__init__(seed=seed)
        self.num_agents = n
        self.grid = OrthogonalMooreGrid(
            (width, height), torus=True, capacity=10, random=self.random
        )
        # Instantiate DataCollector
        self.datacollector = mesa.DataCollector(
            model_reporters={"Gini": compute_gini},
            agent_reporters={"Wealth": "wealth", "Steps_not_given": "steps_not_given"},
        )
        self.running = True

        # Create agents
        agents = MoneyAgent.create_agents(
            self,
            self.num_agents,
            self.random.choices(self.grid.all_cells.cells, k=self.num_agents),
        )

    def step(self):
        # Collect data each step
        self.datacollector.collect(self)
        self.agents.shuffle_do("move")
        self.agents.do("give_money")

def main():
    log_file = get_log_file_directory() / "output_log.txt"

    with Logger(filename=log_file):
        print("World System Beta Phase 1 Starting")
        print("World System Beta Phase 1 Starting")
        print("World System Beta Phase 1 Starting")

    params = {"width": 10, "height": 10, "n": range(5, 105, 5)}

    results = mesa.batch_run(
        MoneyModel,
        parameters=params,
        iterations=5,
        max_steps=100,
        number_processes=1,
        data_collection_period=1,
        display_progress=True,
    )

    results_df = pd.DataFrame(results)
    print(f"The results have {len(results)} rows.")
    print(f"The columns of the data frame are {list(results_df.keys())}.")

    # Filter the results to only contain the data of one agent
    # The Gini coefficient will be the same for the entire population at any time
    results_filtered = results_df[(results_df.AgentID == 1) & (results_df.Step == 100)]
    results_filtered[["iteration", "n", "Gini"]].reset_index(
        drop=True
    ).head()  # Create a scatter plot
    g = sns.scatterplot(data=results_filtered, x="n", y="Gini")
    g.set(
        xlabel="number of agents",
        ylabel="Gini coefficient",
        title="Gini coefficient vs. Number of Agents",
    )

    plt.show()
    
if __name__ == "__main__":
    main()
