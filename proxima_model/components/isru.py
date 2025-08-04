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
        self.operational_status = config.get("operational_status", "active")
        
        # Current operation state
        self.current_power_demand = 0
        self.ice_extraction_active = False
        self.regolith_extraction_active = False
        
        # Metrics
        self.total_regolith_extracted_kg = 0
        self.total_ice_extracted_kg = 0  # Add this line
        self.total_power_consumed_kWh = 0
    
    def evaluate_extraction_needs(self, available_power, stocks):
        """Determine what extraction operations to perform based on available power and needs."""
        self.current_power_demand = 0
        self.ice_extraction_active = False
        self.regolith_extraction_active = False
        
        if self.operational_status != "active":
            return
        
        remaining_power = min(available_power, self.max_power_usage_kWh)
        
        # Policy: Extract ice if power available (no need to check existing ice stock)
        if remaining_power >= self.ice_extraction_power_kWh:
            self.ice_extraction_active = True
            self.current_power_demand += self.ice_extraction_power_kWh
            remaining_power -= self.ice_extraction_power_kWh
    
        # Policy: Extract regolith if power still available
        if remaining_power >= self.regolith_extraction_power_kWh:
            self.regolith_extraction_active = True
            self.current_power_demand += self.regolith_extraction_power_kWh

    def extract_resources(self, allocated_power, stocks):
        """Perform actual extraction operations with allocated power."""
        extracted_resources = {}
        consumed_resources = {}
        power_consumed = 0
        
        if self.operational_status != "active":
            return extracted_resources, consumed_resources, power_consumed
        
        # Ice extraction - extract ice from lunar surface (convert to water)
        if (self.ice_extraction_active and 
            allocated_power >= self.ice_extraction_power_kWh):
            
            # Apply efficiency - we're mining ice from the surface and melting it to water
            actual_output = self.ice_extraction_output_kg * self.efficiency
            extracted_resources["H2O_kg"] = actual_output  # Changed from "Ice_kg"
            power_consumed += self.ice_extraction_power_kWh
            allocated_power -= self.ice_extraction_power_kWh

        # Regolith extraction - produce regolith from nothing (lunar surface)
        if (self.regolith_extraction_active and 
            allocated_power >= self.regolith_extraction_power_kWh):
        
            # Apply efficiency
            actual_output = self.regolith_extraction_output_kg * self.efficiency
            extracted_resources["FeTiO3_kg"] = actual_output
            power_consumed += self.regolith_extraction_power_kWh
        
            # Update metrics
            self.total_regolith_extracted_kg += actual_output
    
        self.total_power_consumed_kWh += power_consumed
        return extracted_resources, consumed_resources, power_consumed
    
    def get_power_demand(self):
        """Return current power demand."""
        return self.current_power_demand


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
        
        # Regolith processing parameters
        self.regolith_processing_input_kg = config.get("regolith_processing_input_kg", 100)
        self.regolith_processing_o2_output_kg = config.get("regolith_processing_o2_output_kg", 12)
        self.regolith_processing_metal_output_kg = config.get("regolith_processing_metal_output_kg", 10)
        
        # He-3 extraction parameters
        self.he3_extraction_regolith_input_kg = config.get("he3_extraction_regolith_input_kg", 500)
        self.he3_extraction_power_kWh = config.get("he3_extraction_power_kWh", 50)
        self.he3_extraction_output_kg = config.get("he3_extraction_output_kg", 0.1)
        
        self.efficiency = config.get("efficiency", 0.85)
        self.operational_status = config.get("operational_status", "active")
        
        # Current operation state
        self.current_power_demand = 0
        self.electrolysis_active = False
        self.regolith_processing_active = False
        self.he3_extraction_active = False
        
        # Metrics
        self.total_h2_generated_kg = 0
        self.total_o2_generated_kg = 0
        self.total_metal_generated_kg = 0
        self.total_he3_generated_kg = 0
        self.total_power_consumed_kWh = 0
    
    def evaluate_generation_needs(self, available_power, stocks):
        """Determine what generation operations to perform."""
        self.current_power_demand = 0
        self.electrolysis_active = False
        self.regolith_processing_active = False
        self.he3_extraction_active = False
        
        if self.operational_status != "active":
            return
        
        remaining_power = min(available_power, self.max_power_usage_kWh)
        
        # Policy 1: Always try electrolysis if we have water (produces H2 and O2)
        if (stocks.get("H2O_kg", 0) >= self.electrolysis_water_input_kg and
            remaining_power >= self.electrolysis_power_kWh):
            self.electrolysis_active = True
            self.current_power_demand += self.electrolysis_power_kWh
            remaining_power -= self.electrolysis_power_kWh
    
        # Policy 2: Process regolith for O2 and metal if we have regolith
        elif (stocks.get("FeTiO3_kg", 0) >= self.regolith_processing_input_kg):
            self.regolith_processing_active = True
            # Regolith processing doesn't require power in our model
    
        # Policy 3: He-3 extraction only if we have lots of regolith (rare)
        if (stocks.get("FeTiO3_kg", 0) >= self.he3_extraction_regolith_input_kg and 
            remaining_power >= self.he3_extraction_power_kWh):
            self.he3_extraction_active = True
            self.current_power_demand += self.he3_extraction_power_kWh
    
    def generate_resources(self, allocated_power, stocks):
        """Perform actual generation operations with allocated power."""
        generated_resources = {}
        consumed_resources = {}
        power_consumed = 0
        
        if self.operational_status != "active":
            return generated_resources, consumed_resources, power_consumed
        
        # He-3 extraction (highest priority)
        if (self.he3_extraction_active and 
            allocated_power >= self.he3_extraction_power_kWh and
            stocks.get("FeTiO3_kg", 0) >= self.he3_extraction_regolith_input_kg):
            
            # Apply efficiency
            actual_output = self.he3_extraction_output_kg * self.efficiency
            generated_resources["He3_kg"] = actual_output
            consumed_resources["FeTiO3_kg"] = self.he3_extraction_regolith_input_kg
            power_consumed += self.he3_extraction_power_kWh
            allocated_power -= self.he3_extraction_power_kWh
            
            # Update metrics
            self.total_he3_generated_kg += actual_output
    
        # Electrolysis - CHANGE elif TO if
        if (self.electrolysis_active and 
              allocated_power >= self.electrolysis_power_kWh and
              stocks.get("H2O_kg", 0) >= self.electrolysis_water_input_kg):
            
            # Apply efficiency
            h2_output = self.electrolysis_h2_output_kg * self.efficiency
            o2_output = self.electrolysis_o2_output_kg * self.efficiency
            
            generated_resources["H2_kg"] = h2_output
            generated_resources["O2_kg"] = o2_output
            consumed_resources["H2O_kg"] = self.electrolysis_water_input_kg
            power_consumed += self.electrolysis_power_kWh
            allocated_power -= self.electrolysis_power_kWh
            
            # Update metrics
            self.total_h2_generated_kg += h2_output
            self.total_o2_generated_kg += o2_output
    
        # Regolith processing - CHANGE elif TO if
        if (self.regolith_processing_active and
              stocks.get("FeTiO3_kg", 0) >= self.regolith_processing_input_kg):
            
            # Apply efficiency
            o2_output = self.regolith_processing_o2_output_kg * self.efficiency
            metal_output = self.regolith_processing_metal_output_kg * self.efficiency
            
            generated_resources["O2_kg"] = o2_output
            generated_resources["Metal_kg"] = metal_output
            consumed_resources["FeTiO3_kg"] = self.regolith_processing_input_kg
            
            # Update metrics
            self.total_o2_generated_kg += o2_output
            self.total_metal_generated_kg += metal_output
        
        self.total_power_consumed_kWh += power_consumed
        return generated_resources, consumed_resources, power_consumed
    
    def get_power_demand(self):
        """Return current power demand."""
        return self.current_power_demand