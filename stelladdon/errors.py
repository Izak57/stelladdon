from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .core import Context


__all__ = [
    "StelladdonError", "ObjectAlreadyExists", "ObjectNotFound",
    "TableNotFound"
]

class StelladdonError(Exception):
    """Base class for all Stelladdon exceptions."""
    pass



class ObjectAlreadyExists(StelladdonError):
    """Raised when trying to insert an object that already exists in the database."""
    pass

class ObjectNotFound(StelladdonError):
    """Raised when an object is not found in the database."""
    pass

class TableNotFound(StelladdonError):
    """Raised when a table is not found in the database."""
    pass



class HTTPException(Exception):
    """
    Base class for all HTTP exceptions.
    """
    
    def __init__(self, ctx: "Context") -> None:
        self.ctx = ctx
        super().__init__()



class StellaAPIError(HTTPException):

    def __init__(self,
                 ctx: "Context",
                 code: str,
                 status_code: int,
                 message: str | None) -> None:
        super().__init__(ctx)
        self.code = code
        self.status_code = status_code
        self.message = message


    @property
    def data(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "statusCode": self.status_code,
            "message": self.message
        }



class NoWaitResponse(HTTPException):

    def __init__(self, response, ctx: "Context") -> None:
        self.response = response
        super().__init__(ctx)



### internal APIs errors ###



class ObjectNotFound(StellaAPIError):

    def __init__(self,
                 ctx: "Context",
                 message: str,
                 key: str,
                 value: Any) -> None:
        super().__init__(ctx, "stellapi.object.notfound", 404, message)
        self.key = key
        self.value = value



class InternalError(StellaAPIError):

    def __init__(self,
                 ctx: "Context",
                 message: str,
                 exception: Exception) -> None:
        super().__init__(ctx, "stellapi.internal_error", 500, message)
        self.exception = exception
