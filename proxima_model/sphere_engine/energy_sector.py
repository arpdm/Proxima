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

    def step(self, power_demand):
        """Single step: process power demand and return what's available."""
        # Process demand through microgrid
        power_supplied = self.microgrid.step(power_demand)
        return power_supplied

    def get_metrics(self):
        """Get metrics for logging."""
        microgrid_metrics = self.microgrid.get_metrics()
        return microgrid_metrics
