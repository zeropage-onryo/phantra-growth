"""`python -m bots.discord` runs the bot; `python -m bots.discord pair`
signs it in to Phantra once and prints the token to set as
PHANTRA_BOT_API_KEY."""
import sys

if len(sys.argv) > 1 and sys.argv[1] == "pair":
    from .api import APIError, pair
    from .config import Settings

    base = Settings.from_env().api_base
    try:
        token = pair(base)
    except APIError as e:
        print(f"not signed in: {e.message}", file=sys.stderr)
        sys.exit(1)
    print("\nSigned in. Set this as the bot's PHANTRA_BOT_API_KEY, then forget it:")
    print(f"\n    {token}\n")
    print("On Fly:  fly secrets set PHANTRA_BOT_API_KEY=<that token>")
    print("Revoke it any time in the studio: Settings -> Connections.")
    sys.exit(0)

from .bot import main  # noqa: E402

sys.exit(main())
