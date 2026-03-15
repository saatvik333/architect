from src.hello import greet


def test_greet() -> None:
    assert greet("World") == "Hello, World!"
