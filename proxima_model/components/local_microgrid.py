"""
local_microgrid.py
=============================

Description:
    This module simulates a local microgrid using a combination of solar arrays (VSATs) and a battery system
    to provide power to a habitat. The simulation is run using the SimPy library to model the passage of time
    and the interactions between components. The simulation includes power generation, load consumption, and 
    battery management over a specified period.

Author:
    Arpi Derm <arpiderm@gmail.com>

Created:
    July 5, 2024

Dependencies:
    - random: Generate pseudo-random numbers (part of Python standard library)
    - math: Mathematical functions (part of Python standard library)
    - proxima_model.environments.lunar_env: Environment variables specific to the local microgrid simulation

License:
    MIT License

Classes:
    - Battery: Represents the battery storage system.
    - VSAT: Represents the solar array using VSAT technology.
    - LocalMicroGrid: Manages the microgrid, including solar power generation, load consumption, and battery management.

Functions:
    - main: The main function to set up and run the simulation.
"""

import random
import math
import pandas as pd

from proxima_model.tools.logger import save_time_series_data_to_file
from proxima_model.environments import lunar_env as env


PROCESS_RUNTIME_PERIOD_H = 1  # Run time period in hours
FLOATING_POINT_PRECISION = 4


class Battery:
    def __init__(self, env, initial_soc: float = 0):
        """
        Model for battery used in the microgrid.

        Args:
            env (simpy.Environment): Environment for simulation.
            initial_soc (float): Initial state of charge of the battery as a fraction of the total capacity.
        """
        self._env = env
        self.state_of_charge = initial_soc
        self.total_charge_kw = 0
        self.battery_soc_ts = []

    def charge(self, power_kw: float, duration_h: float):
        """
        Charge the battery based on provided power and duration.

        Args:
            power_kw (float): Provided power in kW.
            duration_h (float): Charge duration in hours.
        """

        # To keep the battery healthy and extend its lifetime, we dont want to keep the battery charged 100% at all times.
        if self.state_of_charge >= env.BATTERY_MAX_STATE_OF_CHARGE_RATE:
            print(f"Max SoC for battery reached.")
            charge_amount = 0
        else:
            charge_amount = min(power_kw, env.BATTERY_MAX_CHARGE_RATE_KW) * duration_h
            max_energy_allowed = env.BATTERY_CAPACITY_KW_H - (self.state_of_charge * env.BATTERY_CAPACITY_KW_H)
            if charge_amount > max_energy_allowed:
                charge_amount = max(0, max_energy_allowed)

        self._calculatestate_of_charge(charge_amount)
        print(f"SoC {self.state_of_charge} at time {self._env.now} Charge amount: {charge_amount} kWh")
        return charge_amount

    def discharge(self, power_kw: float):
        """
        Discharge battery by the demanded power.

        Args:
            power_kw (float): Demanded power in kW.

        Returns:
            float: Actual power provided by the battery.
        """
        if self.total_charge_kw >= power_kw:
            self._calculatestate_of_charge(-1 * power_kw)
            return power_kw
        else:
            discharged_power = self.state_of_charge * env.BATTERY_CAPACITY_KW_H
            self._calculatestate_of_charge(-1 * discharged_power)
            return discharged_power

    def _calculatestate_of_charge(self, power_kw: float):
        """
        Calculate the state of charge for the battery based on the input power.

        Args:
            power_kw (float): Charging or discharging power in kW.
        """
        self.total_charge_kw += env.BATTERY_CHARGING_EFFICIENCY * power_kw
        self.state_of_charge = self.total_charge_kw / env.BATTERY_CAPACITY_KW_H

        self.battery_soc_ts.append(self.state_of_charge)


class VSAT:
    def __init__(self, env):
        """
        Initialize a VSAT solar array.

        Args:
            env (simpy.Environment): Environment for simulation.
        """
        self.env = env

    def generate(self):
        """
        Generate power using VSAT technology.

        Returns:
            float: Generated solar power in kW.
        """
        angle_of_incidence_degree = random.uniform(
            env.SOLAR_ANGLE_OF_INCIDENCE_MIN_DEG, env.SOLAR_ANGLE_OF_INCIDENCE_MAX_DEG
        )
        g_effective = env.G_W_M2 * math.cos(math.radians(angle_of_incidence_degree))
        generated_power_kw = g_effective * env.VSAT_AREA_M2 * env.VSAT_EFFICIENCY / 1000  # Convert to kW
        print(f"VSAT Generated power: {generated_power_kw} kW at time {self.env.now}")
        return generated_power_kw


class LocalMicroGrid:
    def __init__(self, sim_env, num_panels: int, load_kwh: float, initial_battery_soc: float, num_batteries: int):
        """
        Initialize the local microgrid.

        Args:
            sim_env (simpy.Environment): Environment for simulation.
            num_panels (int): Number of VSAT panels.
            load_kwh (float): Load consumption in kWh.
            initial_battery_soc (float): Initial state of charge for the battery.
        """
        self.data_frame = pd.DataFrame()
        self.batteries_soc_df = pd.DataFrame()

        self._sim_env = sim_env
        self._load_kwh = load_kwh
        self._total_generated_power_kwh = 0
        self._time_ts = []
        self._generated_pw_kw_ts = []
        self._consumed_pw_kw_ts = []
        self._excess_pw_kw_ts = []

        self._batteries = [Battery(self._sim_env, initial_battery_soc) for _ in range(num_batteries)]
        self._battery_soc_ts = {f"battery_{i+1}_soc": [] for i in range(num_batteries)}
        self._batteries_total_charge_kw_ts = []
        self._solar_arrays = [VSAT(self._sim_env) for _ in range(num_panels)]

        # Main power grid control process. It handles power generation, consumption rates, and battery charging.
        self._sim_env.process(self._control())

    def _control(self):
        """
        Control process for the microgrid, handling power generation, load consumption, and battery management.

        Yields:
            simpy.events.Timeout: Simulates the passage of one hour.
        """
        while True:
            # Generate power from all solar arrays
            self.total_generated_power_kwh = 0
            for solar_array in self._solar_arrays:
                generated_power = solar_array.generate()
                self.total_generated_power_kwh += generated_power

            # Control logic to manage load and battery
            excess_power = self.total_generated_power_kwh - self._load_kwh

            if excess_power > 0:
                consumed_power = self._load_kwh
                # Distribute excess power across all batteries
                for battery in self._batteries:
                    if excess_power <= 0:
                        excess_power = 0
                    charged_amount = battery.charge(excess_power, 1)
                    excess_power -= charged_amount
            else:
                consumed_power = self.total_generated_power_kwh
                extra_pwr_needed = self._load_kwh - self.total_generated_power_kwh
                # Use battery power to makeup the deficit
                for battery in self._batteries:
                    if excess_power >= 0:
                        break
                    if self._load_kwh - extra_pwr_needed <= 0:
                        break
                    power_from_battery = battery.discharge(extra_pwr_needed)
                    extra_pwr_needed -= power_from_battery
                    print(
                        f"Power generated: {self.total_generated_power_kwh:.2f} kW, insufficient to meet load: {self._load_kwh:.2f} kW, using {power_from_battery:.2f} kW from battery"
                    )

            total_charge = 0

            for i, battery in enumerate(self._batteries):
                self._battery_soc_ts[f"battery_{i+1}_soc"].append(battery.state_of_charge)
                total_charge += battery.total_charge_kw

            self._batteries_total_charge_kw_ts.append(total_charge)

            # Logging
            self._time_ts.append(self._sim_env.now)
            self._consumed_pw_kw_ts.append(consumed_power)
            self._excess_pw_kw_ts.append(excess_power)
            self._generated_pw_kw_ts.append(self.total_generated_power_kwh)

            # Wait for the next hour
            yield self._sim_env.timeout(PROCESS_RUNTIME_PERIOD_H)

    def save_data(self, file_path: str):
        """Saves all time-series data attributes and states within local microgrid to CSV file

        Args:
            file_path (str): location and file name for local microgrid time-series data
        """

        self.batteries_soc_df = pd.DataFrame(self._battery_soc_ts)
        self.batteries_soc_df["time_h"] = self._time_ts

        self.data_drame = pd.DataFrame(
            {
                "time_h": self._time_ts,
                "generated_pw_kw": self._generated_pw_kw_ts,
                "consumed_pw_kw": self._consumed_pw_kw_ts,
                "excess_pw_kw": self._excess_pw_kw_ts,
                "total_battery_charged_amount_kw": self._batteries_total_charge_kw_ts,
            }
        ).round(FLOATING_POINT_PRECISION)

        save_time_series_data_to_file([self.data_drame], file_path)
