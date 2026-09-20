from pokertable_agent import LLMAgent, make_bot
from pokertable_agent.base import Decision, clamp_decision
from pokertable_agent.parse import parse_decision
from pokertable_agent.providers.echo import EchoProvider
from pokertable.simulate import run

OBS = {"legal_actions": ["fold", "call", "raise"], "min_raise_to": 20, "max_raise_to": 1000, "amount_to_call": 10,
       "hole_cards": ["Ah", "Kh"], "board": [], "pot": 15, "blinds": {"small": 5, "big": 10}, "stack": 1000}


def test_parse_variants():
    assert parse_decision('{"action": "raise", "amount": 30}').action == "raise"
    d = parse_decision('Sure!\n```json\n{"action":"call","say":"nice"}\n```\nGood luck')
    assert d.action == "call" and d.say == "nice"
    assert parse_decision("I will fold here.").action == "fold"
    d = parse_decision("Raise to 45 please")
    assert d.action == "raise" and d.amount == 45
    assert parse_decision("ALL IN").amount == 10**9


def test_clamp_makes_intent_legal_without_inventing_aggression():
    assert clamp_decision(Decision("raise", 5), OBS).amount == 20
    assert clamp_decision(Decision("raise", 99999), OBS).amount == 1000
    assert clamp_decision(Decision("check"), OBS).action == "call"
    assert clamp_decision(Decision("bet", 50), {**OBS, "legal_actions": ["fold", "call"]}).action == "call"
    assert clamp_decision(Decision("dance"), {**OBS, "legal_actions": ["fold", "check"]}).action == "check"


def test_bots_and_llm_loop_complete_a_simulation():
    agents = {"tag": make_bot("tag", 1), "call": make_bot("call"), "rnd": make_bot("random", 2), "llm": LLMAgent(EchoProvider(), persona="solid")}
    game, stats = run(agents, hands=50, seed=3)
    assert game.hand_number == 50 and game.status == "finished"
    assert set(stats) == set(agents)
    assert sum(s["net_chips"] for s in stats.values()) == 0
