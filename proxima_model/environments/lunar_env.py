# ==================== Environment Parameters

ENVIRONMENT_NAME = "Lunar South Pole"
SOLAR_ANGLE_OF_INCIDENCE_MIN_DEG = 1.5
SOLAR_ANGLE_OF_INCIDENCE_MAX_DEG = 3.0
G_W_M2 = 1361  # Solar irradiance (w/m2)

# ==================== Initial Simulation Parameters

HABITAT_NUM = 1
HABITAT_PWR_CONSUMPTION_RATE_KWH = 30

VSAT_NUM = 4

BAT_SOC_INI = 0.1  # Initial battery charge state

# ==================== Simulation

RUN_TIME_H = 24  # Total simulation runtime

# ==================== Power Grid

# Battery Specifications
BATTERY_MAX_CHARGE_RATE_KW = 4
BATTERY_CAPACITY_KW_H = 40
BATTERY_MAX_STATE_OF_CHARGE_RATE = 0.8
BATTERY_CHARGING_EFFICIENCY = 0.95

# VSAT Specifications
VSAT_EFFICIENCY = 0.25  # Reference efficiency at standard test conditions
VSAT_AREA_M2 = 45  # Individual solar array area (m^2)
B = 0.0045  # Temperature coefficient of efficency
T_REF_DEG_C = 25  # Reference temparatue
