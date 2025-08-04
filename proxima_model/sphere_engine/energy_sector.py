"""
energy_sector.py

Simplified energy sector management.
"""

from proxima_model.components.energy_microgrid import MicrogridManager


class EnergySector:
    """Simplified energy sector with single-step processing."""
    
    def __init__(self, model, config):
        self.model = model
        self.microgrid = MicrogridManager(model, config)
        
        # Simple cumulative tracking
        self.total_energy_generated = 0.0
        self.total_energy_consumed = 0.0
        self.total_energy_shortage = 0.0
        
    def step(self, power_demand):
        """Single step: process power demand and return what's available."""
        # Process demand through microgrid
        power_supplied = self.microgrid.step(power_demand)
        return power_supplied
    
    def get_metrics(self):
        """Get metrics for logging."""
        microgrid_metrics = self.microgrid.get_metrics()
        return microgrid_metrics
    
    def get_state(self):
        """Get complete state for UI."""
        return self.microgrid.get_detailed_state()