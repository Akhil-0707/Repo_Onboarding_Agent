from . import services


def register(app):
    service = services.UserService()

    @app.get("/users/<int:user_id>")
    def get_user(user_id: int):
        user = service.get_user(user_id)
        return {"id": user.id, "name": user.name} if user else ({}, 404)

    return app
