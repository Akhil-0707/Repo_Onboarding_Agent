from flask import Flask

from app.routes import register

from .config import Settings


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SETTINGS"] = Settings()
    return register(app)


def cli() -> None:
    create_app().run(port=Settings().port)


if __name__ == "__main__":
    cli()
