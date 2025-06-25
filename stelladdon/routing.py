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


__all__ = [
    "Context", "Route", "StellAppMaster",
    "StellaRouter"
]



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


    def raise_api_error(self,
                        code: str,
                        status_code: int,
                        message: str | None = None) -> None:
        raise StellaAPIError(
            self,
            code=code,
            status_code=status_code,
            message=message
        )


    async def call_before_service(self, service: Service):
        resp = await run_with_context(service.before_fn, self.arguments, self)
        return resp


    def paginate(self,
                 items: list[Any],
                 listname: str | None = None,
                 has_next_page: bool | None = None) -> dict[str, Any]:
        listinfo = self.pagination[listname]
        start = (listinfo.page - 1) * listinfo.per_page
        end = start + listinfo.per_page
        data = items[start:end]

        if has_next_page is None:
            has_next_page = len(items[end:]) > 0

        return self.as_paginable(
            data,
            listname=listinfo.name,
            has_next_page=has_next_page
        )


    def as_paginable(self,
                     items: list,
                     listname: str | None = None,
                     has_next_page: bool = True) -> dict[str, Any]:
        listinfo = self.pagination[listname]

        return {
            "@stellaType": "paginable",
            "listname": listinfo.name,
            "page": listinfo.page,
            "perPage": listinfo.per_page,
            "nextPage": listinfo.page + 1 if has_next_page else None,
            "items": items,
        }


    def serialize(self, data: Any) -> dict[str, Any]:
        """
        Serialize the data using the route serialization method.
        """
        return self.route.encode_response(data)


    def jsonstrify(self, data: Any) -> str:
        """
        Serialize the data using the route serialization method.
        And return a JSON string.
        """
        return jsonable_encoder(self.serialize(data))


    @property
    def master(self) -> "StellAppMaster":
        return self.route.master
    

    @property
    def pagination(self) -> PaginationInfo:
        if self._paginfo is not None:
            return self._paginfo

        pagination_info = PaginationInfo(self)
        for key, value in self.req.query_params.items():
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

        self._paginfo = pagination_info
        return pagination_info



class Route:

    def __init__(self,
                 upper: "StellAppMaster | StellaRouter | None",
                 fn: Callable,
                 services: list[Service]) -> None:
        self.upper = upper
        self.fn = fn
        self.services = services
        self.faroute: APIRoute | None = None


    @property
    def master(self) -> "StellAppMaster":
        return self.upper.master


    def get_arguments(self) -> dict[str, Any]:
        path_param_names = get_path_param_names(self.faroute.path)
        fnannotations = get_annotations(self.fn)

        arguments: dict[str, Any] = {}

        for pathparam in path_param_names:
            if pathparam in fnannotations:
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
                        key=annot_val.key or pathparam,
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


    def get_services(self) -> List[Service]:
        return self.services + self.upper.get_services()


    async def __call__(self, req: Request):
        context = Context(req, self)
        arguments: dict[str, Any] = {}
        from inspect import signature

        try:
            arguments = self.process_arguments(context)

            for service in self.get_services():
                if service.before_fn:
                    service_result = await run_with_context(service.before_fn, arguments, context)

            response = await run_with_context(self.fn, arguments, context)

            for service in self.get_services():
                if service.after_fn:
                    afterservice_result = service.after_fn(context, response)
                    if iscoroutinefunction(service.after_fn):
                        afterservice_result = await afterservice_result

                    if afterservice_result:
                        response = afterservice_result

        except Exception as e:
            errortype = type(e)

            best_handler = next((
                handler for handler in self.master.get_error_handlers()
                if issubclass(errortype, handler.errortype)), None)
            
            if best_handler:
                response = await best_handler.handler(e, context)

            else:
                raise e

        response = self.encode_response(response)
        return response



class StellaRouter:

    def __init__(self,
                 router: APIRouter,
                 services: list[Service] | None = None) -> None:
        self.routers: list["StellaRouter"] = []
        self.routes: List[Route] = []
        self.farouter = router
        self.upper: StellAppMaster | StellaRouter | None = None
        self.error_handlers: List[ErrorHandler] = []
        self.services = services or []


    @property
    def master(self) -> "StellAppMaster":
        return self.upper.master


    def errorhandler(self, errortype: type[Exception]) -> Callable:
        def decorator(func: Callable) -> Callable:
            handler = ErrorHandler(errortype, func)
            self.error_handlers.append(handler)
            return func
        return decorator


    def get_services(self) -> List[Service]:
        if self.upper:
            return self.services + self.upper.get_services()
        return self.services


    def route(self,
              method: str,
              path: str,
              services: list[Service] | None = None) -> Callable:
        def decorator(func: Callable) -> Callable:
            route = Route(self, func, services or [])
            self.routes.append(route)
            func.__route__ = route

            self.farouter.add_api_route(path, route.__call__, methods=[method])
            faroute = self.farouter.routes[-1] # TODO: inject metadata then find
            route.faroute = faroute

        return decorator


    def include_router(self, router: "StellaRouter") -> None:
        router.upper = self
        self.routers.append(router)
        self.farouter.include_router(router.farouter)


    def get_error_handlers(self) -> List[ErrorHandler]:
        return self.error_handlers + self.upper.get_error_handlers() if self.upper else []



class StellAppMaster(StellaRouter):

    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.error_handlers: List[ErrorHandler] = []
        super().__init__(self.app.router, services=[])

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
                resp = exc.ctx.master.app.default_response_class(resp)

            return resp


    @property
    def master(self) -> "StellAppMaster":
        return self


    def get_error_handlers(self) -> List[ErrorHandler]:
        return self.error_handlers
