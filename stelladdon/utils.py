from typing import Any, Optional
from rich.console import Console


def _pretty(obj: Any) -> str:
    console = Console(record=True)
    console.print(obj)
    return console.export_text(styles=True).strip()
