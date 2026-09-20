"""Event type names recorded by the engine. Kept in one place for replay and export code."""

HAND_STARTED = "hand_started"
BLIND = "blind"
DEAL_HOLE = "deal_hole"  # private
ACTION = "action"
STREET = "street"
SHOWDOWN = "showdown"
SETTLEMENT = "settlement"

PUBLIC = {HAND_STARTED, BLIND, ACTION, STREET, SHOWDOWN, SETTLEMENT}
