import time
import sys
from typing import Callable

from .theme import HermesColor, HermesStyle


def boot_sequence(
    print_fn: Callable = print,
    delay: float = 0.15,
    clear: Callable | None = None,
) -> None:
    lines = [
        ("Core Systems", " ONLINE"),
        ("Sentinel Layer", " ONLINE"),
        ("Memory Fabric", " ONLINE"),
        ("Governance Engine", " ONLINE"),
    ]
    if clear:
        clear()
    print_fn("\n[ INITIALIZING HERMES-PRIME ]\n")
    for i in range(len(lines)):
        for j, (label, status) in enumerate(lines):
            marker = " [.]" if j > i else (" [.]" if j == i else " [\u2713]")
            if j < i:
                print_fn(f"  {label} ............. ONLINE")
            elif j == i:
                print_fn(f"  {label} ............. [.]")
            else:
                print_fn(f"  {label} .............")
        if i < len(lines) - 1:
            time.sleep(delay)
            if clear:
                clear()
            print_fn("\n[ INITIALIZING HERMES-PRIME ]\n")
    time.sleep(delay)
    if clear:
        clear()
    print_fn("\n[ INITIALIZING HERMES-PRIME ]\n")
    for label, _ in lines:
        print_fn(f"  {label} ............. ONLINE")
    print_fn(f"\n  SYSTEM STATUS :: OPERATIONAL\n")


def pulse_loader(
    label: str = "SIGNAL ACQUISITION",
    steps: int = 5,
    delay: float = 0.12,
    print_fn: Callable = print,
) -> None:
    frames = [
        "[■□□□□□□□□□]",
        "[■■■□□□□□□□]",
        "[■■■■■■□□□□]",
        "[■■■■■■■■■□]",
        "[■■■■■■■■■■]",
    ]
    done_label = "SIGNAL LOCK ACQUIRED"
    for i in range(steps):
        frame = frames[i] if i < len(frames) else frames[-1]
        lbl = label if i < steps - 1 else done_label
        print_fn(f"\r  {frame} {lbl}", end="")
        time.sleep(delay)
    print()


def governance_verification(
    print_fn: Callable = print,
    delay: float = 0.2,
    clear: Callable | None = None,
) -> None:
    layers = [
        "Sentinel Policy Engine",
        "Runtime Constraint Matrix",
        "Cognitive Safety Layer",
        "Recursive Stability Checks",
    ]
    if clear:
        clear()
    print_fn("\n" + "═" * 40)
    print_fn(" VERIFYING GOVERNANCE LAYERS")
    print_fn("═" * 40 + "\n")
    for i in range(len(layers) + 1):
        for j, layer in enumerate(layers):
            if j < i:
                print_fn(f"  [\u2713] {layer}")
            elif j == i:
                print_fn(f"  [\u00B7] {layer}")
            else:
                print_fn(f"  [ ] {layer}")
        if i < len(layers):
            time.sleep(delay)
            if clear:
                clear()
            print_fn("\n" + "═" * 40)
            print_fn(" VERIFYING GOVERNANCE LAYERS")
            print_fn("═" * 40 + "\n")
    print_fn(f"\n  {'=' * 14}")
    print_fn("  SYSTEM VERIFIED")
    print_fn(f"  {'=' * 14}\n")


def watchdog_spinner(
    ticks: int = 6,
    delay: float = 0.2,
    print_fn: Callable = print,
) -> None:
    frames = ["\u25C9\u25CB\u25CB", "\u25CB\u25C9\u25CB", "\u25CB\u25CB\u25C9"]
    for i in range(ticks):
        frame = frames[i % len(frames)]
        print_fn(f"\r  [ WATCHDOG ]  {frame}", end="")
        time.sleep(delay)
    print()


def typewriter(
    text: str,
    delay: float = 0.015,
    print_fn: Callable = print,
    end: str = "\n",
) -> None:
    for char in text:
        print_fn(char, end="", flush=True)
        time.sleep(delay)
    print_fn(end="", flush=True)
    if end:
        print_fn(end="")
