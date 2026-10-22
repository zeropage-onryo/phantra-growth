"""`python -m bots.reddit_listener [--once]` runs the listener."""
import sys

from .listener import main

sys.exit(main())
