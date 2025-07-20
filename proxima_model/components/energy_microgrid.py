import numpy as np

class Battery:
    def __init__(self, initial_battery_soc_kwh, max_operation_capacitiy_kwh, min_operation_capacity_kwh, delta_t_hours):
        self.charge_level = initial_battery_soc_kwh
        self.state_of_charge = self.charge_level / max_operation_capacitiy_kwh
        self.min_operation_capacity_kwh = min_operation_capacity_kwh
        self.max_operation_capacitiy_kwh = max_operation_capacitiy_kwh
        self.dt = delta_t_hours

    def chrage_discharge(self, charge_request_kw):
        new_charge = self.charge_level + charge_request_kw * self.dt
        self.charge_level = np.clip(new_charge, self.min_operation_capacity_kwh, self.max_operation_capacitiy_kwh)
        self.state_of_charge = self.charge_level / self.min_operation_capacity_kwh


class VSAT:
    def __init__(self, max_capacity_kwh):
        self.generated_power_watt = 0
        self.max_capacity_kwh = max_capacity_kwh
    def generate_power(self, power_gen_request_watts):
        self.generated_power_watt = min(self.max_capacity_kwh, power_gen_request_watts)
        return self.generated_power_watt


class FuelCell:
    def __init__(self, max_capacity_kwh):
        self.generated_power_watt = 0
        self.max_capacity_kwh = max_capacity_kwh

    def generate_power(self, power_gen_request_watts):
        self.generated_power_watt = min(self.max_capacity_kwh, power_gen_request_watts)
        return self.generated_power_watt