"""Enable ``python -m oe_sdk`` as an alias for the ``oe-sdk`` console script."""

from oe_sdk.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
