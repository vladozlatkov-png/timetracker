"""One hand of No-Limit Texas Hold'em, wrapped around PokerKit.

The wrapper owns the deck (from the Dealer), maps table seats to PokerKit
player indices, validates actions, advances streets, and records an
append-only event list from which the hand can be replayed.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Any

from pokerkit import Automation, Mode, NoLimitTexasHoldem

PHASES = ["preflop", "flop", "turn", "river"]

# PokerKit emits advisory warnings (e.g. "no reason to fold"). They are not errors.
warnings.filterwarnings("ignore", category=UserWarning, module="pokerkit")

AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.RUNOUT_COUNT_SELECTION,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)


class IllegalAction(Exception):
    def __init__(self, message: str, legal: LegalActions | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.legal = legal


@dataclass(frozen=True)
class SeatEntry:
    seat: int
    name: str
    stack: int


@dataclass
class LegalActions:
    actions: list[str]
    call_amount: int = 0
    min_raise_to: int | None = None
    max_raise_to: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "actions": list(self.actions),
            "call_amount": self.call_amount,
            "min_raise_to": self.min_raise_to,
            "max_raise_to": self.max_raise_to,
        }


@dataclass
class HandResult:
    hand_id: int
    payoffs: dict[int, int]
    final_stacks: dict[int, int]
    hole_cards: dict[int, list[str]]
    shown_cards: dict[int, list[str]]
    board: list[str]
    winners: list[int]
    went_to_showdown: list[int]


@dataclass
class Hand:
    hand_id: int
    seats: list[SeatEntry]  # in clockwise table order, any starting point
    button_seat: int
    small_blind: int
    big_blind: int
    deck: list[str]
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.seats) < 2:
            raise ValueError("a hand needs at least two players")
        if len(self.deck) != 52 or len(set(self.deck)) != 52:
            raise ValueError("deck must contain 52 distinct cards")
        self._order = self._seat_order()
        self._index_of = {seat: i for i, seat in enumerate(self._order)}
        by_seat = {s.seat: s for s in self.seats}
        self._names = {s.seat: s.name for s in self.seats}
        self._state = NoLimitTexasHoldem.create_state(
            AUTOMATIONS,
            False,
            0,
            (self.small_blind, self.big_blind),
            self.big_blind,
            tuple(by_seat[seat].stack for seat in self._order),
            len(self._order),
            mode=Mode.CASH_GAME,
        )
        self._deck_pos = 0
        self._hole: dict[int, list[str]] = {seat: [] for seat in self._order}
        self._board: list[str] = []
        self._actions: list[dict[str, Any]] = []
        self._result: HandResult | None = None
        self._record(
            "hand_started",
            button_seat=self.button_seat,
            seats=[{"seat": s.seat, "name": s.name, "stack": s.stack} for s in self.seats],
            small_blind=self.small_blind,
            big_blind=self.big_blind,
        )
        for seat, bet in zip(self._order, self._state.bets):
            if bet:
                self._record("blind", seat=seat, amount=int(bet))
        self._deal_hole_cards()
        self._advance()

    # ---- setup -----------------------------------------------------------

    def _seat_order(self) -> list[int]:
        """PokerKit index 0 is the small blind. Heads-up, the button is the small blind."""
        seats = [s.seat for s in self.seats]
        if self.button_seat not in seats:
            raise ValueError("button seat is not in the hand")
        b = seats.index(self.button_seat)
        if len(seats) == 2:
            # PokerKit heads-up: index 0 is the big blind, index 1 is the button/small blind.
            return [seats[(b + 1) % 2], seats[b]]
        return [seats[(b + 1 + i) % len(seats)] for i in range(len(seats))]

    def _next_card(self) -> str:
        card = self.deck[self._deck_pos]
        self._deck_pos += 1
        return card

    def _deal_hole_cards(self) -> None:
        while self._state.can_deal_hole():
            idx = self._state.hole_dealee_index
            card = self._next_card()
            self._state.deal_hole(card)
            self._hole[self._order[idx]].append(card)
        for seat in self._order:
            self._record("deal_hole", seat=seat, cards=list(self._hole[seat]), private=True)

    # ---- state accessors -------------------------------------------------

    @property
    def finished(self) -> bool:
        return not self._state.status

    @property
    def phase(self) -> str:
        if self.finished:
            return "complete"
        return PHASES[min(self._state.street_index or 0, 3)]

    @property
    def actor_seat(self) -> int | None:
        idx = self._state.actor_index
        return None if idx is None else self._order[idx]

    @property
    def board(self) -> list[str]:
        return list(self._board)

    @property
    def hand_actions(self) -> list[dict[str, Any]]:
        return list(self._actions)

    def hole_cards(self, seat: int) -> list[str]:
        return list(self._hole[seat])

    def all_hole_cards(self) -> dict[int, list[str]]:
        return {s: list(c) for s, c in self._hole.items()}

    def stack(self, seat: int) -> int:
        return int(self._state.stacks[self._index_of[seat]])

    def bet(self, seat: int) -> int:
        return int(self._state.bets[self._index_of[seat]])

    def status(self, seat: int) -> str:
        i = self._index_of[seat]
        if not self._state.statuses[i]:
            return "folded"
        if self._state.stacks[i] == 0:
            return "all_in"
        return "active"

    def positions(self) -> dict[int, str]:
        n = len(self._order)
        labels: dict[int, str] = {}
        if n == 2:
            labels[self._order[0]] = "BB"
            labels[self._order[1]] = "BTN/SB"
            return labels
        names = ["SB", "BB"] + ["UTG"] + [f"UTG+{i}" for i in range(1, max(0, n - 5))]
        names = names[:n]
        tail = ["BTN", "CO", "HJ"][: max(0, n - len(names))]
        names = names + tail[::-1] if tail else names
        # ensure last is BTN
        names = names[: n - 1] + ["BTN"]
        for seat, label in zip(self._order, names):
            labels[seat] = label
        return labels

    @property
    def pot_total(self) -> int:
        return int(self._state.total_pot_amount)

    def pots(self) -> list[dict[str, Any]]:
        return [
            {"amount": int(p.amount), "seats": [self._order[i] for i in p.player_indices]}
            for p in self._state.pots
        ]

    def legal_actions(self, seat: int | None = None) -> LegalActions:
        actor = self.actor_seat
        if actor is None or (seat is not None and seat != actor):
            return LegalActions(actions=[])
        st = self._state
        actions: list[str] = []
        if st.can_fold():
            actions.append("fold")
        call_amount = int(st.checking_or_calling_amount or 0)
        if st.can_check_or_call():
            actions.append("check" if call_amount == 0 else "call")
        min_to = st.min_completion_betting_or_raising_to_amount
        max_to = st.max_completion_betting_or_raising_to_amount
        if st.can_complete_bet_or_raise_to():
            actions.append("bet" if max(st.bets) == 0 else "raise")
        else:
            min_to = max_to = None
        return LegalActions(
            actions=actions,
            call_amount=call_amount,
            min_raise_to=None if min_to is None else int(min_to),
            max_raise_to=None if max_to is None else int(max_to),
        )

    # ---- mutation --------------------------------------------------------

    def apply(self, seat: int, action: str, amount: int | None = None) -> dict[str, Any]:
        """Apply one action for ``seat``. Raises IllegalAction without changing state."""
        if self.finished:
            raise IllegalAction("hand is complete")
        if seat != self.actor_seat:
            raise IllegalAction(f"seat {seat} is not the acting seat", self.legal_actions())
        legal = self.legal_actions(seat)
        st = self._state
        action = (action or "").lower().strip()
        phase = self.phase
        if action == "fold":
            if "fold" not in legal.actions:
                raise IllegalAction("fold is not available", legal)
            st.fold()
            applied = {"action": "fold", "amount": 0}
        elif action in ("check", "call"):
            if "check" not in legal.actions and "call" not in legal.actions:
                raise IllegalAction(f"{action} is not available", legal)
            if action == "check" and legal.call_amount > 0:
                raise IllegalAction(f"cannot check facing a bet of {legal.call_amount}; call or fold", legal)
            paid = min(legal.call_amount, self.stack(seat))
            st.check_or_call()
            applied = {"action": "check" if legal.call_amount == 0 else "call", "amount": paid}
        elif action in ("bet", "raise"):
            if legal.min_raise_to is None:
                raise IllegalAction("betting or raising is not available", legal)
            if amount is None:
                raise IllegalAction("amount is required for bet/raise", legal)
            amount = int(amount)
            if not st.can_complete_bet_or_raise_to(amount):
                raise IllegalAction(
                    f"amount {amount} is not legal; raise-to range is {legal.min_raise_to}-{legal.max_raise_to}",
                    legal,
                )
            st.complete_bet_or_raise_to(amount)
            applied = {"action": "bet" if "bet" in legal.actions else "raise", "amount": amount}
        else:
            raise IllegalAction(f"unknown action '{action}'", legal)
        event = {"seat": seat, "phase": phase, **applied}
        self._actions.append(event)
        self._record("action", **event)
        self._advance()
        return event

    def _advance(self) -> None:
        st = self._state
        while st.status and (st.can_burn_card() or st.can_deal_board()):
            if st.can_burn_card():
                st.burn_card("??")  # unknown card: PokerKit's internal deck is never consulted
                continue
            count = st.board_dealing_count
            cards = [self._next_card() for _ in range(count)]
            st.deal_board("".join(cards))
            self._board.extend(cards)
            phase = {3: "flop", 4: "turn", 5: "river"}[len(self._board)]
            self._record("street", phase=phase, cards=cards, board=list(self._board))
        if not st.status:
            self._settle()

    def _settle(self) -> None:
        st = self._state
        shown: dict[int, list[str]] = {}
        for op in st.operations:
            if type(op).__name__ == "HoleCardsShowingOrMucking" and op.hole_cards:
                shown[self._order[op.player_index]] = [repr(c) for c in op.hole_cards]
        payoffs = {seat: int(p) for seat, p in zip(self._order, st.payoffs)}
        folded = {a["seat"] for a in self._actions if a["action"] == "fold"}
        went = [s for s in self._order if s not in folded] if len(self._board) == 5 else []
        if len(went) < 2:
            went = []
        received: dict[int, int] = {seat: 0 for seat in self._order}
        for op in st.operations:
            if type(op).__name__ == "ChipsPushing":
                for i, amt in enumerate(op.amounts):
                    received[self._order[i]] += int(amt)
        winners = [s for s in self._order if received[s] > 0]
        for seat in self._order:
            if seat in shown:
                self._record("showdown", seat=seat, cards=shown[seat])
        self._result = HandResult(
            hand_id=self.hand_id,
            payoffs=payoffs,
            final_stacks={seat: self.stack(seat) for seat in self._order},
            hole_cards=self.all_hole_cards(),
            shown_cards=shown,
            board=list(self._board),
            winners=winners,
            went_to_showdown=went,
        )
        self._record("settlement", payoffs=payoffs, winners=winners, final_stacks=self._result.final_stacks)

    @property
    def result(self) -> HandResult | None:
        return self._result

    def _record(self, kind: str, **data: Any) -> None:
        self.events.append({"seq": len(self.events), "type": kind, **data})

    # ---- serialisation ---------------------------------------------------

    def public_events(self) -> list[dict[str, Any]]:
        return [e for e in self.events if not e.get("private")]

    def record(self, include_private: bool) -> dict[str, Any]:
        r = self._result
        return {
            "hand_id": self.hand_id,
            "button_seat": self.button_seat,
            "small_blind": self.small_blind,
            "big_blind": self.big_blind,
            "board": list(self._board),
            "events": self.events if include_private else self.public_events(),
            "hole_cards": {str(k): v for k, v in self._hole.items()} if include_private else {},
            "shown_cards": {str(k): v for k, v in (r.shown_cards if r else {}).items()},
            "payoffs": {str(k): v for k, v in (r.payoffs if r else {}).items()},
            "final_stacks": {str(k): v for k, v in (r.final_stacks if r else {}).items()},
            "winners": r.winners if r else [],
            "went_to_showdown": r.went_to_showdown if r else [],
        }
