from dataclasses import dataclass


class HermesColor:
    CYAN = "cyan"
    WHITE = "white"
    AMBER = "yellow"
    RED = "red"
    GREEN = "green"
    BLACK = "black"
    GREY = "grey62"
    DARK_GREY = "grey35"
    BOLD = "bold"
    DIM = "dim"
    ITALIC = "italic"


@dataclass
class HermesStyle:
    core_signal: str = "bold cyan"
    governance: str = "bold white"
    warning: str = "bold yellow"
    critical: str = "bold red"
    success: str = "bold green"
    meta: str = "grey62"
    dim: str = "grey35"
    label: str = "grey62"
    value: str = "white"
    header: str = "bold white on black"
    border: str = "grey62"
    prompt: str = "bold cyan"
    error: str = "bold red"
    highlight: str = "cyan"


HERMES_THEME = {
    "core_signal": "bold cyan",
    "governance": "bold white",
    "warning": "bold yellow",
    "critical": "bold red",
    "success": "bold green",
    "meta": "grey62",
    "dim": "grey35",
    "label": "grey62",
    "value": "white",
    "header": "bold white on black",
    "border": "grey62",
    "prompt": "bold cyan",
    "error": "bold red",
    "highlight": "cyan",
}
