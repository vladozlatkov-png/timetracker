"""Rules edge cases: split pots, side pots, short all-ins, heads-up order, replay."""

from pokertable.core import Dealer, Hand, IllegalAction, SeatEntry


def seats(*stacks):
    return [SeatEntry(i + 1, f"p{i + 1}", s) for i, s in enumerate(stacks)]


def test_blinds_and_first_actor_three_handed():
    h = Hand(1, seats(1000, 1000, 1000), button_seat=3, small_blind=5, big_blind=10, deck=Dealer(seed=1).shuffled_deck())
    assert h.bet(1) == 5 and h.bet(2) == 10
    assert h.actor_seat == 3
    assert h.positions() == {1: "SB", 2: "BB", 3: "BTN"}


def test_heads_up_button_is_small_blind_and_acts_first():
    h = Hand(1, seats(1000, 1000), button_seat=1, small_blind=5, big_blind=10, deck=Dealer(seed=1).shuffled_deck())
    assert h.bet(1) == 5 and h.bet(2) == 10
    assert h.actor_seat == 1
    h.apply(1, "call")
    h.apply(2, "check")
    assert h.phase == "flop"
    assert h.actor_seat == 2, "big blind acts first postflop heads-up"


def test_split_pot(deck):
    # order [BB=seat2, BTN=seat1]; round robin: seat2 Ah, seat1 Ad, seat2 Kc, seat1 Kd; board broadway
    d = deck("Ah", "Ad", "Kc", "Kd", "Qs", "Js", "Ts", "2c", "3c")
    h = Hand(1, seats(1000, 1000), button_seat=1, small_blind=5, big_blind=10, deck=d)
    h.apply(1, "raise", 30)
    h.apply(2, "call")
    for _ in range(3):
        h.apply(2, "check")
        h.apply(1, "check")
    assert h.finished
    assert h.result.payoffs == {1: 0, 2: 0}
    assert sorted(h.result.winners) == [1, 2]
    assert sorted(h.result.went_to_showdown) == [1, 2]


def test_side_pots_three_way_all_in(deck):
    # seats: 1 (SB, 100), 2 (BB, 400), 3 (BTN, 1000). Deal order SB, BB, BTN.
    d = deck("Ah", "Kd", "2s", "Ad", "Kh", "7d", "Th", "7c", "9d", "3h", "4c")
    h = Hand(1, seats(100, 400, 1000), button_seat=3, small_blind=5, big_blind=10, deck=d)
    h.apply(3, "raise", 1000)
    h.apply(1, "call")
    h.apply(2, "call")
    assert h.finished
    # AA (seat1) wins main pot 300; KK (seat2) wins side pot of 600 vs 72o; seat3 loses 400
    assert h.result.payoffs == {1: 200, 2: 200, 3: -400}
    assert h.result.final_stacks == {1: 300, 2: 600, 3: 600}
    assert sum(h.result.payoffs.values()) == 0


def test_short_stack_can_only_call_all_in():
    h = Hand(1, seats(1000, 25, 1000), button_seat=3, small_blind=5, big_blind=10, deck=Dealer(seed=2).shuffled_deck())
    h.apply(3, "raise", 30)
    h.apply(1, "fold")
    legal = h.legal_actions(2)
    assert legal.actions == ["fold", "call"] and legal.call_amount == 15
    h.apply(2, "call")
    assert h.finished
    assert abs(h.result.payoffs[2]) == 25 or h.result.payoffs[2] == 30


def test_all_in_raise_below_minimum_reopens_nothing():
    h = Hand(1, seats(1000, 35, 1000), button_seat=3, small_blind=5, big_blind=10, deck=Dealer(seed=2).shuffled_deck())
    h.apply(3, "raise", 30)
    h.apply(1, "fold")
    legal = h.legal_actions(2)
    assert legal.min_raise_to == legal.max_raise_to == 35
    h.apply(2, "raise", 35)
    legal3 = h.legal_actions(3)
    assert "raise" not in legal3.actions, "a short all-in does not reopen betting"
    assert legal3.call_amount == 5


def test_illegal_actions_do_not_mutate_state():
    h = Hand(1, seats(1000, 1000, 1000), button_seat=3, small_blind=5, big_blind=10, deck=Dealer(seed=3).shuffled_deck())
    before = (h.actor_seat, h.stack(3), len(h.events))
    for seat, action, amount in [(1, "call", None), (3, "check", None), (3, "raise", 15), (3, "raise", 5000), (3, "dance", None)]:
        try:
            h.apply(seat, action, amount)
            assert False, f"{action} should be illegal"
        except IllegalAction as e:
            assert e.message
    assert (h.actor_seat, h.stack(3), len(h.events)) == before


def test_chips_conserved_over_many_random_hands():
    import random

    rng = random.Random(5)
    dealer = Dealer(seed=5)
    stacks = {1: 1000, 2: 1000, 3: 1000, 4: 1000}
    button = 1
    for n in range(300):
        players = [SeatEntry(s, f"p{s}", st) for s, st in stacks.items() if st > 0]
        if len(players) < 2:
            break
        seats_ = [p.seat for p in players]
        button = next((s for s in seats_ if s > button), seats_[0])
        h = Hand(n, players, button_seat=button, small_blind=5, big_blind=10, deck=dealer.shuffled_deck())
        while not h.finished:
            a = h.actor_seat
            legal = h.legal_actions(a)
            act = rng.choice(legal.actions)
            amt = rng.randint(legal.min_raise_to, legal.max_raise_to) if act in ("bet", "raise") else None
            h.apply(a, act, amt)
        for s, st in h.result.final_stacks.items():
            stacks[s] = st
        assert sum(stacks.values()) == 4000
        assert sum(h.result.payoffs.values()) == 0


def test_record_replays_to_same_settlement():
    h = Hand(1, seats(1000, 1000, 1000), button_seat=3, small_blind=5, big_blind=10, deck=Dealer(seed=9).shuffled_deck())
    while not h.finished:
        a = h.actor_seat
        legal = h.legal_actions(a)
        h.apply(a, "call" if "call" in legal.actions else "check")
    rec = h.record(include_private=True)
    # rebuild the deck from the record: hole cards in deal order then board
    order = [e["seat"] for e in rec["events"] if e["type"] == "deal_hole"]
    hole = {e["seat"]: e["cards"] for e in rec["events"] if e["type"] == "deal_hole"}
    dealt = [hole[s][i] for i in range(2) for s in order] + rec["board"]
    from pokertable.core.dealer import new_deck

    deck = dealt + [c for c in new_deck() if c not in dealt]
    h2 = Hand(1, seats(1000, 1000, 1000), button_seat=3, small_blind=5, big_blind=10, deck=deck)
    for e in [e for e in rec["events"] if e["type"] == "action"]:
        h2.apply(e["seat"], e["action"], e.get("amount") or None)
    assert h2.result.payoffs == h.result.payoffs
    assert h2.board == h.board
