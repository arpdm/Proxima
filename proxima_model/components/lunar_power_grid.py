"""
lunar_microgrid_simulation.py
=============================

Description:
    This module simulates a lunar microgrid using a combination of solar arrays (VSATs) and a battery system
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
    - proxima_model.environments.lunar_env: Environment variables specific to the lunar simulation

Usage:
    To run the simulation, execute this script using a Python interpreter:
        $ python lunar_microgrid_simulation.py

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
from proxima_model.environments import lunar_env as env


class Battery:
    def __init__(self, env, initial_soc: float = 0):
        """
        Model for battery used in the microgrid.

        Args:
            env (simpy.Environment): Environment for simulation.
            initial_soc (float): Initial state of charge of the battery as a fraction of the total capacity.
        """
        self.env = env
        self.state_of_charge = initial_soc

    def charge(self, power_kw: float, duration_h: float):
        """
        Charge the battery based on provided power and duration.

        Args:
            power_kw (float): Provided power in kW.
            duration_h (float): Charge duration in hours.
        """
        charge_amount = min(power_kw, env.BATTERY_MAX_CHARGE_RATE_KW) * duration_h
        max_energy_allowed = env.BATTERY_CAPACITY_KW_H - (self.state_of_charge * env.BATTERY_CAPACITY_KW_H)
        if charge_amount > max_energy_allowed:
            charge_amount = max(0, max_energy_allowed)

        self.calculate_state_of_charge(charge_amount)
        print(f"SoC {self.state_of_charge} at time {self.env.now} Charge amount: {charge_amount} kWh")

    def discharge(self, power_kw: float):
        """
        Discharge battery by the demanded power.

        Args:
            power_kw (float): Demanded power in kW.

        Returns:
            float: Actual power provided by the battery.
        """
        if (self.state_of_charge * env.BATTERY_CAPACITY_KW_H) >= power_kw:
            self.calculate_state_of_charge(-1 * power_kw)
            return power_kw
        else:
            discharged_power = self.state_of_charge * env.BATTERY_CAPACITY_KW_H
            self.calculate_state_of_charge(-1 * discharged_power)
            return discharged_power

    def calculate_state_of_charge(self, power_kw: float):
        """
        Calculate the state of charge for the battery based on the input power.

        Args:
            power_kw (float): Charging or discharging power in kW.
        """
        self.state_of_charge += (env.BATTERY_CHARGING_EFFICIENCY * power_kw) / env.BATTERY_CAPACITY_KW_H


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
    def __init__(self, sim_env, num_panels: int, load_kwh: float, initial_battery_soc: float):
        """
        Initialize the local microgrid.

        Args:
            sim_env (simpy.Environment): Environment for simulation.
            num_panels (int): Number of VSAT panels.
            load_kwh (float): Load consumption in kWh.
            initial_battery_soc (float): Initial state of charge for the battery.
        """
        self.sim_env = sim_env
        self.load_kwh = load_kwh
        self.battery = Battery(self.sim_env, initial_battery_soc)
        self.solar_arrays = [VSAT(self.sim_env) for _ in range(num_panels)]
        self.total_generated_power_kwh = 0
        self.generated_power_ts = []
        self.load_consumption_ts = []

        # Main power grid control process. It handles power generation, consumption rates, and battery charging.
        self.sim_env.process(self.control())

    def control(self):
        """
        Control process for the microgrid, handling power generation, load consumption, and battery management.

        Yields:
            simpy.events.Timeout: Simulates the passage of one hour.
        """
        while True:
            # Generate power from all solar arrays
            self.total_generated_power_kwh = 0
            for solar_array in self.solar_arrays:
                generated_power = solar_array.generate()
                self.total_generated_power_kwh += generated_power

            self.generated_power_ts.append(self.total_generated_power_kwh)

            # Control logic to manage load and battery
            excess_power = self.total_generated_power_kwh - self.load_kwh
            if excess_power > 0:
                self.battery.charge(excess_power, 1)
                self.load_consumption_ts.append(self.load_kwh)
            else:
                # Use battery power to makeup the deficit
                power_from_battery = self.battery.discharge(self.load_kwh - self.total_generated_power_kwh)
                total_power_provided = self.total_generated_power_kwh + power_from_battery
                self.load_consumption_ts.append(total_power_provided)
                print(
                    f"Power generated: {self.total_generated_power_kwh:.2f} kW, insufficient to meet load: {self.load_kwh:.2f} kW, using {power_from_battery:.2f} kW from battery"
                )

            # Wait for the next hour
            yield self.sim_env.timeout(1)
