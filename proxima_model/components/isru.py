"""
ISRU (In-Situ Resource Utilization) Agents for lunar resource extraction and generation.
"""

import numpy as np
from mesa import Agent


class ISRUExtractor(Agent):
    """ISRU Extraction Agent - handles ice and regolith extraction."""

    def __init__(self, model, config):
        super().__init__(model)

        # Configuration from template
        self.agent_type = "isru"
        self.subtype = "extractor"
        self.max_power_usage_kWh = config.get("max_power_usage_kWh", 15)
        self.ice_extraction_power_kWh = config.get("ice_extraction_power_kWh", 5)
        self.ice_extraction_output_kg = config.get("ice_extraction_output_kg", 20)
        self.regolith_extraction_power_kWh = config.get("regolith_extraction_power_kWh", 10)
        self.regolith_extraction_output_kg = config.get("regolith_extraction_output_kg", 100)
        self.efficiency = config.get("efficiency", 0.9)
        self.processing_time_t = config.get("processing_time_t", 3)
        self.extraction_modes = config.get("extraction_modes", ["ICE", "REGOLITH"])

        # Set initial operational mode to first available mode
        self.operational_mode = self.extraction_modes[0] if self.extraction_modes else "ICE"

    def set_operational_mode(self, mode):
        """Set the operational mode for this extractor."""
        if mode in self.extraction_modes:
            self.operational_mode = mode
            print(f"Extractor operational mode set to: {mode}")
        else:
            print(f"Invalid mode {mode}. Available modes: {self.extraction_modes}")

    def get_power_demand(self):
        """Return current power demand based on operational mode."""
        if self.operational_mode == "ICE":
            return self.ice_extraction_power_kWh
        elif self.operational_mode == "REGOLITH":
            return self.regolith_extraction_power_kWh
        else:
            return 0

    def extract_resources(self, allocated_power):
        """Perform actual extraction operations with allocated power."""
        extracted_resources = {}
        power_consumed = 0

        # Ice extraction mode
        if self.operational_mode == "ICE" and allocated_power >= self.ice_extraction_power_kWh:
            # Apply efficiency - we're mining ice from the surface and melting it to water
            actual_output = self.ice_extraction_output_kg * self.efficiency
            extracted_resources["H2O_kg"] = actual_output
            power_consumed = self.ice_extraction_power_kWh

        # Regolith extraction mode
        elif self.operational_mode == "REGOLITH" and allocated_power >= self.regolith_extraction_power_kWh:
            # Apply efficiency
            actual_output = self.regolith_extraction_output_kg * self.efficiency
            extracted_resources["FeTiO3_kg"] = actual_output
            power_consumed = self.regolith_extraction_power_kWh

        return extracted_resources, power_consumed


class ISRUGenerator(Agent):
    """ISRU Generation Agent - handles electrolysis, regolith processing, and He-3 extraction."""

    def __init__(self, model, config):
        super().__init__(model)

        # Configuration from template
        self.agent_type = "isru"
        self.subtype = "generator"
        self.max_power_usage_kWh = config.get("max_power_usage_kWh", 65)

        # Electrolysis parameters
        self.electrolysis_power_kWh = config.get("electrolysis_power_kWh", 15)
        self.electrolysis_water_input_kg = config.get("electrolysis_water_input_kg", 2.7)
        self.electrolysis_h2_output_kg = config.get("electrolysis_h2_output_kg", 0.3)
        self.electrolysis_o2_output_kg = config.get("electrolysis_o2_output_kg", 2.4)

        # Regolith processing parameters (for METAL mode)
        self.regolith_processing_input_kg = config.get("regolith_processing_input_kg", 100)
        self.regolith_processing_o2_output_kg = config.get("regolith_processing_o2_output_kg", 12)
        self.regolith_processing_metal_output_kg = config.get("regolith_processing_metal_output_kg", 10)

        # He-3 extraction parameters
        self.he3_extraction_regolith_input_kg = config.get("he3_extraction_regolith_input_kg", 500)
        self.he3_extraction_power_kWh = config.get("he3_extraction_power_kWh", 50)
        self.he3_extraction_output_kg = config.get("he3_extraction_output_kg", 0.1)

        self.efficiency = config.get("efficiency", 0.85)
        self.processing_time_t = config.get("processing_time_t", 5)
        self.generator_modes = config.get("generator_modes", ["HE3", "METAL", "ELECTROLYSIS"])

        # Set initial operational mode to first available mode
        self.operational_mode = self.generator_modes[0] if self.generator_modes else "ELECTROLYSIS"

    def set_operational_mode(self, mode):
        """Set the operational mode for this generator."""
        if mode in self.generator_modes:
            self.operational_mode = mode
            print(f"Generator operational mode set to: {mode}")
        else:
            print(f"Invalid mode {mode}. Available modes: {self.generator_modes}")

    def get_power_demand(self):
        """Return current power demand based on operational mode."""
        if self.operational_mode == "ELECTROLYSIS":
            return self.electrolysis_power_kWh
        elif self.operational_mode == "HE3":
            return self.he3_extraction_power_kWh
        elif self.operational_mode == "METAL":
            return 0  # Regolith processing doesn't need power
        else:
            return 0

    def generate_resources(self, allocated_power, stocks):
        """Perform actual generation operations with allocated power."""
        generated_resources = {}
        consumed_resources = {}
        power_consumed = 0

        # Electrolysis mode
        if (
            self.operational_mode == "ELECTROLYSIS"
            and allocated_power >= self.electrolysis_power_kWh
            and stocks.get("H2O_kg", 0) >= self.electrolysis_water_input_kg
        ):

            # Apply efficiency
            h2_output = self.electrolysis_h2_output_kg * self.efficiency
            o2_output = self.electrolysis_o2_output_kg * self.efficiency

            generated_resources["H2_kg"] = h2_output
            generated_resources["O2_kg"] = o2_output
            consumed_resources["H2O_kg"] = self.electrolysis_water_input_kg
            power_consumed = self.electrolysis_power_kWh

        # He-3 extraction mode
        elif (
            self.operational_mode == "HE3"
            and allocated_power >= self.he3_extraction_power_kWh
            and stocks.get("FeTiO3_kg", 0) >= self.he3_extraction_regolith_input_kg
        ):

            # Apply efficiency
            actual_output = self.he3_extraction_output_kg * self.efficiency
            generated_resources["He3_kg"] = actual_output
            consumed_resources["FeTiO3_kg"] = self.he3_extraction_regolith_input_kg
            power_consumed = self.he3_extraction_power_kWh

        # Metal processing mode (no power required)
        elif self.operational_mode == "METAL" and stocks.get("FeTiO3_kg", 0) >= self.regolith_processing_input_kg:

            # Apply efficiency
            o2_output = self.regolith_processing_o2_output_kg * self.efficiency
            metal_output = self.regolith_processing_metal_output_kg * self.efficiency

            generated_resources["O2_kg"] = o2_output
            generated_resources["Metal_kg"] = metal_output
            consumed_resources["FeTiO3_kg"] = self.regolith_processing_input_kg
            power_consumed = 0  # No power required for regolith processing

        return generated_resources, consumed_resources, power_consumed
