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
        self.extraction_modes = config.get("extraction_modes", ["ICE", "REGOLITH", "INACTIVE"])
        self._processing_time = self.processing_time_t

        # Set initial operational mode to first available mode
        self.operational_mode = self.extraction_modes[0] if self.extraction_modes else "ICE"

    def set_operational_mode(self, mode):
        """Set the operational mode for this extractor."""
        if mode in self.extraction_modes:
            self.operational_mode = mode
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

        # Check if we have enough power to operate
        power_needed = self.get_power_demand()
        if allocated_power < power_needed:
            return {}, 0  # Can't operate without sufficient power

        # Consume power for processing
        power_consumed = power_needed

        # Decrement processing time
        if self._processing_time > 0:
            self._processing_time -= 1
            # Still processing - no output yet but consuming power
            return {}, power_consumed

        # Processing complete - generate output and reset timer
        if self.operational_mode == "ICE":
            actual_output = self.ice_extraction_output_kg * self.efficiency
            extracted_resources["H2O_kg"] = actual_output

        elif self.operational_mode == "REGOLITH":
            actual_output = self.regolith_extraction_output_kg * self.efficiency
            extracted_resources["FeTiO3_kg"] = actual_output

        # Reset processing time for next cycle
        self._processing_time = self.processing_time_t
        return extracted_resources, power_consumed


class ISRUGenerator(Agent):
    """ISRU Generation Agent - handles electrolysis, regolith processing, and He-3 extraction."""

    def __init__(self, model, config):
        super().__init__(model)

        # Configuration from template
        self.agent_type = "isru"
        self.subtype = "generator"
        self.max_power_usage_kWh = config.get("max_power_usage_kWh", 65)

        # Process Environment Resources
        for res in model.config.get("resources", []):
            if res.get("resource") == "helium3":
                self.helium_concenteration_limits = res

        # He-3 extraction parameters
        self.he3_regolith_processing_throughput_kg_per_step = config.get(
            "he3_regolith_processing_throughput_tons_per_step", 100 * 1e3
        )  # Throughput kg/step
        self.he3_extraction_power_kWh = config.get("he3_extraction_power_kWh", 50)
        self.he3_c_min_ppb, self.he3_c_max_ppb = (
            self.helium_concenteration_limits["density_ppb"][0],
            self.helium_concenteration_limits["density_ppb"][1],
        )
        self.he3_c_mode_ppb = (self.he3_c_min_ppb + self.he3_c_max_ppb) / 2

        self.efficiency = config.get("efficiency", 0.85)
        self.generator_modes = config.get("generator_modes", ["HE3", "INACTIVE"])

        # Set initial operational mode to first available mode
        self.operational_mode = self.generator_modes[0] if self.generator_modes else "INACTIVE"

    def set_operational_mode(self, mode):
        """Set the operational mode for this generator."""
        if mode in self.generator_modes:
            self.operational_mode = mode
        else:
            print(f"Invalid mode {mode}. Available modes: {self.generator_modes}")

    def get_power_demand(self):
        """Return current power demand based on operational mode using a mapping."""
        mode_power_map = {"HE3": self.he3_extraction_power_kWh, "INACTIVE": 0}
        return mode_power_map.get(self.operational_mode, 0)

    def generate_he3(self, stocks):
        """Generation logic for HE3 mode."""
        generated_resources = {}
        consumed_resources = {}
        power_consumed = self.he3_extraction_power_kWh

        self.helium_concentration_ppb = np.random.triangular(
            self.he3_c_min_ppb, self.he3_c_mode_ppb, self.he3_c_max_ppb
        )
        actual_output = (
            self.he3_regolith_processing_throughput_kg_per_step * self.helium_concentration_ppb * 1e-9 * self.efficiency
        )
        print("HE3 Generated", actual_output)
        generated_resources["He3_kg"] = actual_output
        return generated_resources, consumed_resources, power_consumed

    def generate_inactive(self, stocks):
        """No operation for INACTIVE mode."""
        return {}, {}, 0

    def generate_resources(self, allocated_power, stocks):
        """Perform generation operations based on operational mode."""
        mode_func_map = {
            "HE3": self.generate_he3,
            "INACTIVE": self.generate_inactive,
        }
        func = mode_func_map.get(self.operational_mode, self.generate_inactive)
        power_needed = self.get_power_demand()
        if allocated_power < power_needed:
            return {}, {}, 0  # Can't operate - insufficient power
        return func(stocks)
