from dataclasses import dataclass


@dataclass
class User:
    id: int
    name: str


class UserService:
    """In-memory user store."""

    def __init__(self) -> None:
        self._users = {1: User(1, "ada")}

    def get_user(self, user_id: int) -> User | None:
        return self._users.get(user_id)

    def list_users(self) -> list[User]:
        return list(self._users.values())
