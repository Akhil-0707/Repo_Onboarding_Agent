import os


class Settings:
    """Runtime configuration read from the environment."""

    def __init__(self) -> None:
        self.debug = os.environ.get("DEBUG") == "1"
        self.port = int(os.environ.get("PORT", "5000"))
