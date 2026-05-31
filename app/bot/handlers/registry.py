"""Handler registry — maps intent labels to handler instances."""


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict = {}

    def register(self, handler) -> None:
        self._handlers[handler.intent] = handler

    def get(self, intent: str):
        return self._handlers.get(intent)

    def all_intents(self) -> frozenset:
        return frozenset(self._handlers.keys())


REGISTRY = HandlerRegistry()
