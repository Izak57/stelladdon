from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .routing import Context


__all__ = [
    "PaginableListInfo", "PaginationInfo"
]



class PaginableListInfo:

    def __init__(self,
                 name: str | None,
                 per_page: int | None = None,
                 page: int = 1) -> None:
        self.name = name
        self.per_page = per_page or 5
        self.page = page


    def __repr__(self) -> str:
        return f"[ {self.name} // {self.per_page}:{self.page} ]"



class PaginationInfo:

    def __init__(self, ctx: "Context") -> None:
        self.ctx = ctx
        self.list_infos: list[PaginableListInfo] = []


    def __getitem__(self, listname: str | None) -> PaginableListInfo:
        listinfo = next((li for li in self.list_infos if li.name == listname), None)
        if listinfo is None:
            listinfo = PaginableListInfo(name=listname, per_page=None, page=1)
            self.list_infos.append(listinfo)
        return listinfo


    @property
    def default(self) -> PaginableListInfo:
        return self[None]


    def __repr__(self) -> str:
        return "{ %s }" % ", ".join([li.__repr__() for li in self.list_infos])
