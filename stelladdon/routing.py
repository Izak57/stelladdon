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
from pydantic import BaseModel

from .typin import ServiceT, ServiceResultT
from .database import Table
from .core import StellaAPIError, run_with_context, APIObject, DatabaseGetterArg, FromDatabaseArg, ErrorHandler
from .services import Service
from .errors import StellaAPIError, NoWaitResponse
from .pagination import PaginationInfo, PaginableListInfo



class Context:

    def __init__(self,
                 req: Request,
                 route: "Route") -> None:
        self.req = req
        self.route = route
        self.arguments: dict[str, Any] = {}
        self.states: dict[str, Any] = {}
        self._paginfo: PaginationInfo | None = None


    def inject_arg(self, name: str, value: Any) -> None:
        self.arguments[name] = value


    @property
    def master(self) -> "StellAppMaster":
        return self.route.master
    

    @property
    def pagination(self) -> PaginationInfo:
        if self._pagination_info is not None:
            return self._pagination_info

        pagination_info = PaginationInfo(self)
        for key, value in self.request.query_params.items():
            if key.startswith("page@"):
                name = key.split("@")[1] or None
                page = int(value)

                listinfo = next((li for li in pagination_info.list_infos if li.name == name), None)
                if listinfo:
                    listinfo.page = page
                else:
                    listinfo = PaginableListInfo(name=name, page=page)
                    pagination_info.list_infos.append(listinfo)

            elif key.startswith("perPage@"):
                name = key.split("@")[1] or None
                per_page = int(value)

                listinfo = next((li for li in pagination_info.list_infos if li.name == name), None)
                if listinfo:
                    listinfo.per_page = per_page
                else:
                    listinfo = PaginableListInfo(name=name, per_page=per_page)
                    pagination_info.list_infos.append(listinfo)

        self._pagination_info = pagination_info
        return pagination_info



class Route:

    def __init__(self,
                 master: "StellAppMaster",
                 fn: Callable,
                 services: list[Service]) -> None:
        self.master = master
        self.fn = fn
        self.services = services
        self.faroute: APIRoute | None = None


    def get_arguments(self) -> dict[str, Any]:
        path_param_names = get_path_param_names(self.faroute.path)
        fnannotations = get_annotations(self.fn)

        arguments: dict[str, Any] = {}
        print("ANNOTATIONS:", fnannotations)

        for pathparam in path_param_names:
            if pathparam in fnannotations:
                print(fnannotations[pathparam])
                annot_val = fnannotations[pathparam]

                if get_origin(annot_val) is Annotated:
                    typed_as, annot_val = get_args(annot_val)
                    none_allowed = get_origin(typed_as) is Union and (type(None) in get_args(typed_as)
                                                                      or None in get_args(typed_as))
                else:
                    none_allowed = False

                if isinstance(annot_val, FromDatabaseArg):
                    if ":" in pathparam:
                        pathparam = pathparam.split(":")[0]

                    generic_type: Table = annot_val.table

                    arguments[pathparam] = DatabaseGetterArg(
                        table=generic_type,
                        pyname=pathparam,
                        key=pathparam,
                        none_allowed=none_allowed,
                        only_one=not annot_val.multiple
                    )
            if pathparam not in self.fn.__code__.co_varnames:
                raise ValueError(f"Path parameter '{pathparam}' is not defined in the function '{self.fn.__name__}'.")
        return arguments


    def process_arguments(self, ctx: Context) -> dict[str, Any]:
        ... # TODO: ca
        arguments = {}

        for pyname, arg in self.get_arguments().items():
            print(f"Processing argument: {pyname} -> {arg}")
            if isinstance(arg, DatabaseGetterArg):
                if arg.only_one:
                    obj = arg.table.find_one({arg.key: ctx.req.path_params[pyname]})
                    if  obj is None and not arg.none_allowed:
                        ... # TODO: raise error
                        print("ERROR: Object not found in database for", pyname)
                    arguments[pyname] = obj

                else:
                    objs = arg.table.find({arg.key: ctx.req.path_params[pyname]})
                    arguments[pyname] = objs

        return arguments
    

    def encode_response(self, response: Any) -> Any:
        if isinstance(response, APIObject):
            return response.get_api_data("public")

        elif isinstance(response, (list, tuple, dict)):
            # If the response is a list of APIObjects, encode each one
            return jsonable_encoder(response, custom_encoder={
                APIObject: self.encode_response
            })

        elif isinstance(response, JSONResponse):
            return JSONResponse(
                content=self.encode_response(loads(response.body)),
                status_code=response.status_code,
                headers=response.headers,
                media_type=response.media_type,
                background=response.background,
            )

        return response


    async def __call__(self, req: Request):
        context = Context(req, self)
        arguments: dict[str, Any] = {}

        try:
            arguments = self.process_arguments(context)
            print(arguments)

            for service in self.services:
                if service.before_fn:
                    service_result = await run_with_context(service.before_fn, arguments, context)

            response = await run_with_context(self.fn, arguments, context)
            
            for service in self.services:
                if service.after_fn:
                    afterservice_result = service.after_fn(context, response)
                    if iscoroutinefunction(service.after_fn):
                        afterservice_result = await afterservice_result

                    if afterservice_result:
                        response = afterservice_result

        except Exception as e:
            errortype = type(e)

            best_handler = next((
                handler for handler in self.master.error_handlers
                if issubclass(errortype, handler.errortype)), None)
            
            if best_handler:
                response = await best_handler.handler(e, context)

            else:
                raise e

        response = self.encode_response(response)
        return response



class StellAppMaster:

    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.routes: List[Route] = []
        self.error_handlers: List[ErrorHandler] = []

        @self.app.exception_handler(StellaAPIError)
        async def stella_error_handler(request: Request, exc: StellaAPIError):
            return JSONResponse(
                content=exc.data,
                status_code=exc.status_code,
            )

        @self.app.exception_handler(NoWaitResponse)
        async def nowait_response_handler(request: Request, exc: NoWaitResponse):
            resp = exc.ctx.route.encode_response(exc.response)
            if not isinstance(resp, Response):
                resp = exc.ctx.controller.router.default_response_class(resp)

            return resp


    def errorhandler(self, errortype: type[Exception]) -> Callable:
        """
        A decorator to register an error handler for a specific exception type.
        """
        def decorator(func: Callable) -> Callable:
            handler = ErrorHandler(errortype, func)
            self.error_handlers.append(handler)
            return func
        return decorator


    def route(self,
              method: str,
              path: str,
              services: list[Service] | None = None) -> None:
        def decorator(func: Callable) -> Callable:
            route = Route(self, func, services or [])
            self.routes.append(route)
            func.__route__ = route

            # TODO: check and change path to create customizable path serialization
            self.app.add_api_route(path, route.__call__, methods=[method])
            faroute = self.app.routes[-1] # TODO: inject metadata then find
            route.faroute = faroute

        return decorator
