from typing import Annotated, Callable, List, Any, _SpecialForm, TYPE_CHECKING, get_origin, get_args, Union
from inspect import iscoroutinefunction, get_annotations
from contextlib import AsyncExitStack
from abc import ABC, abstractmethod
from json import loads

from fastapi import FastAPI, Request, APIRouter
from fastapi.routing import APIRoute, run_endpoint_function
from fastapi.utils import get_path_param_names
from fastapi.dependencies.utils import get_dependant, solve_dependencies
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder
from .errors import StellaAPIError, NoWaitResponse
from pydantic import BaseModel

from .typin import ServiceT, ServiceResultT
from .database import Table

if TYPE_CHECKING:
    from .routing import Context


__all__ = [
    "APIObject", "FromDB"
]



async def run_with_context(func: Callable,
                           arguments: dict[str, Any],
                           ctx: "Context") -> Any:
    arguments["stella"] = ctx
    for arg, argval in ctx.arguments.items():
        arguments[arg] = argval

    result = await _run_func(func, arguments, ctx.route.faroute.path, ctx.req)
    return result


async def _run_func(func: Callable,
                    arguments: dict[str, Any],
                    dependant_path: str,
                    req: Request) -> Any:
    co_varnames = list(func.__code__.co_varnames)
    varnames_to_remove = 0

    func_code = func.__code__

    for argname in arguments.copy():
        if argname in co_varnames:
            co_varnames.remove(argname)
            varnames_to_remove += 1

        else:
            del arguments[argname]

    func.__code__ = func.__code__.replace(
        co_varnames=tuple(co_varnames),
        co_argcount=func.__code__.co_argcount - varnames_to_remove,
        co_nlocals=func.__code__.co_nlocals - varnames_to_remove,
    )

    dependant = get_dependant(
        path=dependant_path, # TODO: ca
        call=func,
    )

    try:
        body = await req.json()
    except:
        body = await req.body()

    async with AsyncExitStack() as async_exit_stack:
        solved = await solve_dependencies(
            request=req,
            dependant=dependant,
            body=body, # type: ignore
            async_exit_stack=async_exit_stack,
            embed_body_fields=False
        )

        func.__code__ = func_code

        resp = await run_endpoint_function(
            dependant=dependant,
            values=solved.values | arguments,
            is_coroutine=iscoroutinefunction(func),
        )

        return resp



class DatabaseGetterArg:

    def __init__(self, table: Table, pyname: str, key: str,
                 none_allowed: bool, only_one: bool): # TODO: model (db obj), py name, key, param name
        self.table = table
        self.pyname = pyname
        self.key = key
        self.none_allowed = none_allowed
        self.only_one = only_one



class ErrorHandler:

    def __init__(self, errortype: type[Exception], handler: Callable):
        self.errortype = errortype
        self.handler = handler



class FromDatabaseArg:

    def __init__(self, table: Table,
                 multiple: bool,
                 key: str | None) -> None:
        self.table = table
        self.multiple = multiple
        self.key = key



class APIObject(BaseModel, ABC):

    @abstractmethod
    def get_api_data(self, mode: str) -> dict[str, Any]:
        return self.model_dump()



def FromDB(table: Table,
           multiple: bool = False,
           key: str | None = None) -> FromDatabaseArg:
    """
    A special type hint to indicate that the argument should be fetched from the database.
    TODO: doc
    """
    return FromDatabaseArg(table, multiple, key)
