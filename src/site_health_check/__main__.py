"""Executable module entry point (`python -m site_health_check`)."""

import sys
from site_health_check.cli import main

if __name__ == "__main__":
    sys.exit(main())
