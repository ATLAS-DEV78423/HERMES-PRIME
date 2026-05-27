def _entry() -> None:
    from hermes_prime.cli import main
    from hermes_prime.recovery import safe_main

    raise SystemExit(safe_main(lambda: main()))


if __name__ == "__main__":
    _entry()
