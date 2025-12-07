"""
metrics.py

Shared data models for metrics and goals across the simulation.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any


class MetricType(Enum):
    """Type of metric for scoring normalization."""

    POSITIVE = "positive"  # Higher values are better
    NEGATIVE = "negative"  # Lower values are better


class MetricStatus(Enum):
    """Metric performance status."""

    WITHIN = "within"
    OUTSIDE = "outside"
    UNKNOWN = "unknown"


class GoalDirection(Enum):
    """Direction for performance goals."""

    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


@dataclass
class PerformanceGoal:
    """Performance goal configuration defining how to evailate a performance metric and used to define policies to reach these goals."""

    goal_id: str
    name: str
    metric_id: str
    target_value: float
    direction: str = "minimize"
    weight: float = 1.0

    def __post_init__(self):
        """Validate goal configuration."""
        if self.weight < 0:
            raise ValueError("Weight must be non-negative")
        if self.direction not in [GoalDirection.MINIMIZE.value, GoalDirection.MAXIMIZE.value]:
            raise ValueError(f"Invalid direction: {self.direction}")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceGoal":
        """Create from dictionary."""
        return cls(
            goal_id=data.get("goal_id"),
            name=data.get("name", "Unknown Goal"),
            metric_id=data.get("metric_id"),
            target_value=float(data.get("target_value", 0.0)),
            direction=data.get("direction", "minimize"),
            weight=float(data.get("weight", 1.0)),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "goal_id": self.goal_id,
            "name": self.name,
            "target": self.target_value,
            "direction": self.direction,
            "weight": self.weight,
        }


@dataclass
class MetricDefinition:
    """Definition of a performance metric (for display/reference only)."""

    id: str
    name: str
    unit: Optional[str] = None
    type: str = "positive"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetricDefinition":
        """Create from dictionary."""
        return cls(
            id=data.get("id"),
            name=data.get("name", data.get("id")),
            unit=data.get("unit"),
            type=data.get("type", "positive"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "id": self.id,
            "name": self.name,
            "unit": self.unit,
            "type": self.type,
        }


@dataclass
class MetricScore:
    """Score report for a single metric indicating how well a performance metric is doing against a set goal."""

    name: str
    unit: Optional[str]
    type: str
    current: float
    status: str
    score: Optional[float]
    goal: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        data = {
            "name": self.name,
            "unit": self.unit,
            "type": self.type,
            "current": self.current,
            "status": self.status,
            "score": self.score,
        }
        if self.goal:
            data["goal"] = self.goal
        return data
