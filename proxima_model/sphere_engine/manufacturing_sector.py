"""
Manufacturing Sector - Manages ISRU operations, stocks, and resource flows.
"""

import numpy as np
from proxima_model.components.isru import ISRUExtractor, ISRUGenerator


class ManufacturingSector:
    """Manages ISRU operations, resource stocks, and manufacturing processes."""
    
    def __init__(self, model, config):
        self.model = model
        self.isru_extractors = []
        self.isru_generators = []
        
        # Initialize ISRU agents
        agents_config = config.get("agents_config", [])
        for agent_cfg in agents_config:
            template_id = agent_cfg["template_id"]
            subtype = agent_cfg["subtype"]
            merged_config = agent_cfg["config"]
            quantity = agent_cfg["quantity"]
            
            # Create agents based on quantity
            for i in range(quantity):
                if subtype == "extractor":
                    from proxima_model.components.isru import ISRUExtractor
                    agent = ISRUExtractor(model, merged_config)
                    self.isru_extractors.append(agent)
                    
                elif subtype == "generator":
                    from proxima_model.components.isru import ISRUGenerator
                    agent = ISRUGenerator(model, merged_config)
                    self.isru_generators.append(agent)
        
        print(f"Manufacturing Sector initialized with:")
        print(f"  - {len(self.isru_extractors)} extractors")
        print(f"  - {len(self.isru_generators)} generators")
        
        # Resource stocks (managed by this sector) - STANDARDIZE TO FeTiO3_kg
        initial_stocks = config.get("initial_stocks", {})
        self.stocks = {
            "H2_kg": 10.0,
            "O2_kg": 50.0,
            "H2O_kg": 600.0,  # Combined water stock
            "FeTiO3_kg": 11000.0,  # Combined regolith stock
            "Metal_kg": 0.0,
            "He3_kg": 0.0,
            # Remove "Ice_kg": 500.0,
        }
        self.stocks.update(initial_stocks)
        
        # Sector metrics
        self.total_power_consumed = 0
        self.step_power_consumed = 0
        self.active_operations = 0
        
    def get_power_demand(self):
        """Calculate total power demand from all ISRU operations."""
        total_demand = 0
        
        # Get demand from extractors
        for extractor in self.isru_extractors:
            extractor.evaluate_extraction_needs(1000, self.stocks)  # Evaluate with high power to get max demand
            total_demand += extractor.get_power_demand()
        
        # Get demand from generators
        for generator in self.isru_generators:
            generator.evaluate_generation_needs(1000, self.stocks)  # Evaluate with high power to get max demand
            total_demand += generator.get_power_demand()
            
        return total_demand
        
    def step(self, available_power):
        """Execute one manufacturing step with available power."""
        # Reset step metrics
        self.active_operations = 0
        self.step_power_consumed = 0
        
        # Phase 1: Evaluate all operations to determine power needs
        for extractor in self.isru_extractors:
            extractor.evaluate_extraction_needs(available_power, self.stocks)
    
        for generator in self.isru_generators:
            generator.evaluate_generation_needs(available_power, self.stocks)
    
        # Calculate total demands
        extraction_demand = sum(e.get_power_demand() for e in self.isru_extractors)
        generation_demand = sum(g.get_power_demand() for g in self.isru_generators)
        total_demand = extraction_demand + generation_demand
        
        print(f"Power demands - Extraction: {extraction_demand}, Generation: {generation_demand}, Available: {available_power}")
        
        # Phase 2: Execute operations one by one with individual power allocation
        remaining_power = available_power
        
        # Execute extraction operations first
        for extractor in self.isru_extractors:
            extractor_demand = extractor.get_power_demand()
            if extractor_demand > 0 and remaining_power >= extractor_demand:
                print(f"Executing extractor with {extractor_demand} kWh")
                extracted_resources, consumed_resources, power_used = extractor.extract_resources(extractor_demand, self.stocks)
                print(f"Extracted: {extracted_resources}, Consumed: {consumed_resources}")
                self._update_stocks_from_extraction(extracted_resources, consumed_resources)
                self.step_power_consumed += power_used
                remaining_power -= power_used
                if power_used > 0:
                    self.active_operations += 1
    
        # Execute generation operations second
        for generator in self.isru_generators:
            generator_demand = generator.get_power_demand()
            if generator_demand > 0 and remaining_power >= generator_demand:
                print(f"Executing generator with {generator_demand} kWh")
                generated_resources, consumed_resources, power_used = generator.generate_resources(generator_demand, self.stocks)
                print(f"Generated: {generated_resources}, Consumed: {consumed_resources}")
                self._update_stocks_from_generation(generated_resources, consumed_resources)
                self.step_power_consumed += power_used
                remaining_power -= power_used
                if power_used > 0:
                    self.active_operations += 1
            elif generator_demand == 0:
                # Try regolith processing which doesn't need power
                generated_resources, consumed_resources, power_used = generator.generate_resources(0, self.stocks)
                if generated_resources:
                    print(f"Generated (no power): {generated_resources}, Consumed: {consumed_resources}")
                    self._update_stocks_from_generation(generated_resources, consumed_resources)
                    self.active_operations += 1
    
        self.total_power_consumed += self.step_power_consumed
        print(f"Manufacturing step complete. Power used: {self.step_power_consumed}, Stocks: {self.stocks}")
        
        # Return remaining power
        return remaining_power

    def _update_stocks_from_extraction(self, extracted_resources, consumed_resources):
        """Update stocks with extracted resources and consumed inputs."""
        # Add extracted resources
        for resource, amount in extracted_resources.items():
            if resource in self.stocks:
                self.stocks[resource] += amount
            else:
                self.stocks[resource] = amount
        
        # Remove consumed resources  
        for resource, amount in consumed_resources.items():
            if resource in self.stocks:
                self.stocks[resource] = max(0, self.stocks[resource] - amount)
    
    def _update_stocks_from_generation(self, generated_resources, consumed_resources):
        """Update stocks with generated and consumed resources."""
        # Add generated resources
        for resource, amount in generated_resources.items():
            if resource in self.stocks:
                self.stocks[resource] += amount
            else:
                self.stocks[resource] = amount
        
        # Remove consumed resources
        for resource, amount in consumed_resources.items():
            if resource in self.stocks:
                self.stocks[resource] = max(0, self.stocks[resource] - amount)
    
    def get_metrics(self):
        """Return manufacturing sector metrics."""
    
        # Sector-level metrics
        sector_metrics = {
            "manufacturing_power_demand": self.get_power_demand(),
            "manufacturing_power_consumed": self.step_power_consumed,
            "manufacturing_total_power_consumed": self.total_power_consumed,
            "manufacturing_active_operations": self.active_operations,
            # Stock levels
            "stock_H2_kg": self.stocks.get("H2_kg", 0),
            "stock_O2_kg": self.stocks.get("O2_kg", 0),
            "stock_H2O_kg": self.stocks.get("H2O_kg", 0),
            "stock_FeTiO3_kg": self.stocks.get("FeTiO3_kg", 0),
            "stock_Metal_kg": self.stocks.get("Metal_kg", 0),
            "stock_He3_kg": self.stocks.get("He3_kg", 0),
            # Remove "stock_Ice_kg": self.stocks.get("Ice_kg", 0),
        }
        
        # Combine all metrics
        all_metrics = {**sector_metrics}
        return all_metrics

    def get_state(self):
        """Return current state for logging."""
        return {
            "stocks": self.stocks.copy(),
            "active_operations": self.active_operations,
            "power_consumed": self.step_power_consumed,
            "extractors": [{"id": i, "active": e.get_power_demand() > 0} for i, e in enumerate(self.isru_extractors)],
            "generators": [{"id": i, "active": g.get_power_demand() > 0} for i, g in enumerate(self.isru_generators)]
        }