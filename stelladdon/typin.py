from typing import TypeVar, ParamSpec, TYPE_CHECKING, Callable, Any

if TYPE_CHECKING:
    from pydantic import BaseModel


__all__ = [
    "ControllerModelT", "ControllerT", "DepP",
    "ServiceT", "ServiceResultT", "TableModelT",
]


DepP = ParamSpec("DepP")
ServiceT = TypeVar("ServiceT", bound=Callable)
ServiceResultT = TypeVar("ServiceResultT", bound=Any)
TableModelT = TypeVar("TableModelT", bound="BaseModel")
