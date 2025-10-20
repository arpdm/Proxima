from collections import defaultdict
from typing import Callable, Dict, List
import threading
import logging

logger = logging.getLogger(__name__)


class EventBus:
    """A thread-safe event bus for publishing and subscribing to events."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()  # For thread safety

    def subscribe(self, event_type: str, callback_fn: Callable):
        """Register a function to be called when an event of a certain type is published."""
        with self._lock:
            if callback_fn not in self._subscribers[event_type]:  # Prevent duplicates
                self._subscribers[event_type].append(callback_fn)

    def unsubscribe(self, event_type: str, callback_fn: Callable):
        """Remove a callback from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(callback_fn)
                except ValueError:
                    logger.warning(f"Callback not found for event {event_type}")

    def publish(self, event_type: str, **kwargs):
        """Publish an event, triggering all subscribed callbacks."""
        with self._lock:
            if event_type not in self._subscribers:
                return

            # Copy the list to avoid issues if subscribers modify during iteration
            callbacks = self._subscribers[event_type][:]

        # Call callbacks outside the lock to avoid blocking
        for callback_fn in callbacks:
            try:
                callback_fn(**kwargs)
            except Exception as e:
                logger.error(f"Error in callback for event {event_type}: {e}")
                # Continue to next callback instead of stopping

    def get_subscriber_count(self, event_type: str) -> int:
        """Get the number of subscribers for an event type (for debugging)."""
        with self._lock:
            return len(self._subscribers.get(event_type, []))
