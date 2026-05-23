"""
Refrlow — Reference-flow architecture for delegated context retrieval.

A bounded subagent dispatch system for use with Claude Code (and similar
LLM coding agents). The main agent dispatches narrow, short-lived subagents
to fetch context, rather than browsing the filesystem itself.

See claude-code-refrlow/DESIGN.md for the architectural overview.
"""

from refrlow.dispatcher import Dispatcher, DispatchPolicy
from refrlow.protocol import (
    DispatchRequest,
    DispatchReport,
    Status,
    Scope,
    Budget,
)

__version__ = "0.1.0"

__all__ = [
    "Dispatcher",
    "DispatchPolicy",
    "DispatchRequest",
    "DispatchReport",
    "Status",
    "Scope",
    "Budget",
]
