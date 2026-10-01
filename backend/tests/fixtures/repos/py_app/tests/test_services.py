from app.services import UserService


def test_get_user():
    assert UserService().get_user(1).name == "ada"
