from collections import defaultdict

class EventBus:
    def __init__(self):
        self._subscribers = defaultdict(list)

    def subscribe(self, event_type: str, callback_fn):
        """Register a function to be called when an event of a certain type is published."""
        self._subscribers[event_type].append(callback_fn)

    def publish(self, event_type: str, **kwargs):
        """Publish an event, triggering all subscribed callbacks."""
        if event_type not in self._subscribers:
            return
        
        for callback_fn in self._subscribers[event_type]:
            callback_fn(**kwargs)