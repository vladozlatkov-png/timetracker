import pytest

from pokertable.core.dealer import new_deck


def rigged_deck(*first: str) -> list[str]:
    """A deck that starts with the given cards, in dealing order (hole cards round-robin, then board)."""
    rest = [c for c in new_deck() if c not in first]
    return list(first) + rest


@pytest.fixture
def deck():
    return rigged_deck
