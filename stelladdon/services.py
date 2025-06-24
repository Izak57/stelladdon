from typing import Callable, TYPE_CHECKING


__all__ = [
    "Service"
]



class Service:

    def __init__(self,
                 name: str,
                 before: Callable | None = None,
                 after: Callable | None = None) -> None:
        self.name = name
        self.before_fn = before
        self.after_fn = after


    def before(self, fn: Callable) -> Callable:
        self.before_fn = fn
        return fn


    def after(self, fn: Callable) -> Callable:
        self.after_fn = fn
        return fn
