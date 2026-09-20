# Independent AI Poker Table

**System definition v0.2 — Python service with browser UI**

Status: review draft, 20 September 2026. Supersedes v0.1 (native macOS application).

## What changed from v0.1

| Topic | v0.1 | v0.2 |
|---|---|---|
| Product form | Native macOS app | Python service + browser page. Runs on a Mac, the home server, or any Linux box. |
| Poker engine | Written from scratch | PokerKit (rules, side pots, showdown) + `phevaluator` (hand strength) |
| Turn notification | WebSocket, MCP notification, polling, webhook — undecided | Long-poll `wait_for_turn` endpoint. Server-Sent Events for the browser. |
| Agents | "Existing agents connect" | A reference agent harness ships in Phase 1 so any LLM can sit down in minutes |
| Evaluation | Results dashboard | Headless simulation runner + poker-tracker statistics with confidence intervals |
| Security | Keychain, TLS, per-agent credentials, commit/reveal | API keys in a config file, localhost or Tailscale only. Nothing cryptographic in Phase 1. |
| Phase 1 scope | UI + engine + REST + credentials + tests | Engine + REST + two scripted bots + one LLM agent + plain web table |

The trust model is unchanged: one authoritative dealer and rules service, per-seat filtered observations, connectors as thin adapters.

---

## 1. Executive definition

A Python service hosts play-money No-Limit Texas Hold'em games between a human player and independently running AI agents. The service deals cards, enforces rules, advances the hand, records every event, and exposes controlled access to agents over HTTP. A browser page shows the table to the human and lets them act.

Agents are external clients. They may run on the same machine, on the LAN, in containers, or in the cloud. They use any model or reasoning process they like. The service never calls a model provider itself. The only thing the service knows about an agent is its API key, its role, and its seat.

**Objectives**

- A genuinely independent dealer and authoritative rules engine.
- Heterogeneous agents at the same table through one HTTP contract.
- No seat can see information its role is not entitled to.
- Completed hands and performance data are inspectable and exportable.
- Thousands of hands can be simulated headless to compare agents statistically.
- Local-first, understandable, auditable.

**Non-goals for the initial release**

- Real-money play, payments, wagering, prizes.
- Public multi-tenant network or internet matchmaking.
- Training or fine-tuning models inside the service.
- Direct database access for player agents.
- Cryptographic deal verification.

---

## 2. Actors, roles and trust boundaries

| Role | May | May not |
|---|---|---|
| Human player | Use the browser table, see own cards and public state, act on turn | Inspect deck, other private cards, future board cards |
| Player agent | Read its seat's observation, wait for its turn, submit one legal action, post table chat | Query another seat, deck order, or the database |
| Observer agent | Read public table state and completed-hand data | Act |
| Analyst agent | Query completed results, statistics, hand histories, and all hole cards of finished games (if the game's visibility policy allows) | Read live hidden state |
| Administrator | Create games, issue keys, assign seats, configure limits, inspect audit log | Nothing hidden, but every admin action is logged |

**Information rule.** Every response is built for one authenticated identity. There is no universal "table state" during a live hand. The service constructs a filtered observation containing only what that identity may know.

| Information | During hand | After hand |
|---|---|---|
| Board, pot, stacks, bets, action history | All participants and observers | In completed history |
| A player's hole cards | That seat only | Per showdown/muck policy; analyst role sees all if game policy is `reveal_all_after_game` |
| Folded or mucked cards | Hidden | Hidden by default, analyst-visible if policy allows |
| Cards shown at showdown | Public | Stored as public result data |
| Deck order, RNG state | Never | Never |

---

## 3. System architecture

```
 External agents            Browser (human, admin)
 REST client / harness      HTML + JS, Server-Sent Events
        │                            │
        ▼                            ▼
 ┌─────────────────────────────────────────────┐
 │ FastAPI                                     │
 │  auth (API key) · role · seat · rate limit  │
 ├─────────────────────────────────────────────┤
 │ Application service                         │
 │  observation filter · legal actions ·       │
 │  action submission · results · chat         │
 ├─────────────────────────────────────────────┤
 │ Authoritative core                          │
 │  dealer (secrets.SystemRandom) · PokerKit   │
 │  rules engine · turn clock · settlement     │
 ├─────────────────────────────────────────────┤
 │ Persistence (SQLite)                        │
 │  games · hands · events · settlements ·     │
 │  request log · chat                         │
 └─────────────────────────────────────────────┘
        ▲
        │
 Headless simulation runner (same core, no HTTP)
```

**Stack**

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Every LLM SDK is Python-first. Easiest for a solo builder. |
| HTTP | FastAPI + uvicorn | Async, typed, auto-generates OpenAPI. Agents get a schema for free. |
| Poker rules | PokerKit | Battle-tested NLHE state machine: blinds, all-ins, side pots, odd chips, showdown order. |
| Hand evaluation | `phevaluator` | Fast 5–7 card evaluator for showdown and for analyst statistics. |
| Database | SQLite via SQLAlchemy | One file. Zero ops. Fine for millions of events. |
| Browser UI | Server-rendered HTML (Jinja2) + htmx + SSE | No build step. No JavaScript framework. |
| MCP adapter | FastMCP (Phase 2) | Wraps the same service functions as tools. |
| Config | `config.toml` + env vars | API keys and limits in one file, never in the database or logs. |
| Tests | pytest | Rules edge cases, leakage tests, idempotency tests. |

**One core, several connectors.** REST, the browser, the MCP adapter, and the simulation runner all call the same application-service functions. They share authentication, authorization, filtering, and validation. No connector contains game logic.

**Deployment.** The service binds to `127.0.0.1` by default. Set `bind = "0.0.0.0"` to listen on the LAN or a Tailscale interface. Remote agents reach it over the Tailscale address. Public internet exposure is out of scope.

---

## 4. Agent-facing capability contract

All endpoints are under `/v1`. Authentication is a bearer API key. The server resolves identity, role, and seat from the key. Full OpenAPI schema is served at `/docs`.

| Capability | REST | MCP tool (Phase 2) |
|---|---|---|
| Discover games | `GET /v1/games` | `list_games` |
| Join assigned seat | `POST /v1/games/{game}/seats/join` | `join_game` |
| Read observation | `GET /v1/games/{game}/observation` | `get_observation` |
| Wait for my turn | `GET /v1/games/{game}/wait?timeout=30` | `wait_for_turn` |
| List legal actions | `GET /v1/games/{game}/legal-actions` | `get_legal_actions` |
| Submit action | `POST /v1/games/{game}/actions` | `submit_action` |
| Post table chat | `POST /v1/games/{game}/chat` | `say` |
| Read hand history | `GET /v1/games/{game}/hands` | `get_hand_history` |
| Read a completed hand | `GET /v1/hands/{hand}` | `get_hand_result` |
| Read statistics | `GET /v1/players/{player}/stats` | `get_player_statistics` |
| Export | `GET /v1/games/{game}/export?format=json\|csv\|txt` | — |

**`wait_for_turn`** blocks until it is the caller's turn, the hand ends, or the timeout elapses. It returns the observation. This is the primary agent loop: wait, think, act, repeat. No WebSocket needed.

**Observation** (what a player agent sees on its turn)

```json
{
  "game_id": "table-001",
  "hand_id": 27,
  "state_version": 143,
  "turn_token": "t_9f3a",
  "phase": "flop",
  "my_seat": 3,
  "button_seat": 1,
  "blinds": {"small": 5, "big": 10},
  "hole_cards": ["Ah", "Qs"],
  "board": ["Th", "7c", "2s"],
  "pot": 180,
  "side_pots": [],
  "amount_to_call": 40,
  "min_raise_to": 80,
  "max_raise_to": 1240,
  "legal_actions": ["fold", "call", "raise"],
  "seats": [
    {"seat": 1, "name": "claude-tag", "stack": 980, "bet": 0, "status": "folded", "position": "BTN"},
    {"seat": 2, "name": "gpt-lag", "stack": 1600, "bet": 40, "status": "active", "position": "SB"},
    {"seat": 3, "name": "me", "stack": 1240, "bet": 0, "status": "active", "position": "BB"},
    {"seat": 4, "name": "vlado", "stack": 2180, "bet": 0, "status": "folded", "position": "UTG"}
  ],
  "hand_actions": [
    {"seat": 4, "action": "fold", "phase": "preflop"},
    {"seat": 1, "action": "fold", "phase": "preflop"},
    {"seat": 2, "action": "raise", "amount": 30, "phase": "preflop"},
    {"seat": 3, "action": "call", "amount": 30, "phase": "preflop"},
    {"seat": 2, "action": "bet", "amount": 40, "phase": "flop"}
  ],
  "recent_chat": [{"seat": 2, "text": "Feeling lucky today."}],
  "deadline_utc": "2026-09-20T18:42:10Z"
}
```

Compared with v0.1, the observation now carries the full action sequence of the current hand, every opponent's stack and status, positions relative to the button, and the decision deadline. An agent cannot play sensibly without these.

**Action submission**

```json
POST /v1/games/table-001/actions
{
  "request_id": "req_01J8...",
  "hand_id": 27,
  "turn_token": "t_9f3a",
  "action": "raise",
  "amount": 120
}
```

- `amount` is the total bet-to amount for `bet` and `raise`, absent for `fold`, `check`, `call`.
- The rules engine validates every action. Connectors cannot bypass it.
- An invalid action returns a structured error with the current legal range. The agent may correct it within the remaining time.
- **Idempotency.** `request_id` is unique per attempt. A repeated request returns the original result and never acts twice.
- **Stale turn token** returns HTTP 409 and a fresh observation.

**Table chat** is text only. It is stored separately from actions and can never change game state. Agents see the last few messages in their observation.

---

## 5. Independent dealing and game integrity

The dealer belongs exclusively to the core. No agent supplies cards, chooses the shuffle, advances streets, or settles a pot.

| Control | Requirement |
|---|---|
| Randomness | `secrets.SystemRandom` for shuffling. Seeded `random.Random` allowed only in simulation mode, and the seed is recorded. |
| Shuffle | One complete shuffled deck per hand, created inside the dealer. |
| State transitions | Append-only events: hand start, blinds, deal, action, street, showdown, settlement. |
| Validation | Only the rules engine mutates stacks, bets, pots, status, or turn order. |
| Auditability | Every hand records software version, hand ID, timestamps, all actions, and settlement. |

Deal verification (commit/reveal, multi-party entropy) is deferred indefinitely. The event log is designed so it could be added without touching the agent contract, but for play money among your own agents it is not worth building.

---

## 6. Data and persistence

SQLite, one file, `poker.db`. PostgreSQL is not planned.

| Table | Purpose | Sensitivity |
|---|---|---|
| `identities` | API key hash, name, role, status | Secret |
| `games` | Config: blinds, stacks, seats, timing, visibility policy, status | Operational |
| `seat_assignments` | Identity ↔ seat per game | Security-relevant |
| `hands` | Hand ID, button, dealer seed reference, lifecycle | Restricted while live |
| `card_assignments` | Hole cards per seat, board cards | Hidden while live |
| `action_events` | Ordered actions, amounts, actor, state version, timestamp | Auditable |
| `settlements` | Pots, eligible seats, winners, payouts | Result |
| `chat_messages` | Seat, text, hand ID, timestamp | Deletable |
| `request_log` | Connector, request ID, outcome, latency, error | Operational |

**Access policy.** Player agents never receive database access, not even read-only. They query the service. Analysts get the export endpoints, which are generated only from finalized hands.

**Exports**

- JSON: lossless, full event stream.
- CSV: one row per hand per seat for spreadsheet analysis. This is the Airtable-friendly format.
- Text: PokerStars-style hand history for compatibility with existing trackers.

---

## 7. Hand lifecycle and failure handling

| Step | Behaviour |
|---|---|
| 1. Create game | Admin sets seats, stacks, blinds, decision time, visibility policy, hand limit. |
| 2. Register participants | Each identity gets one role and, if playing, one seat. |
| 3. Start hand | Dealer shuffles. Engine posts blinds and emits `hand_started`. |
| 4. Request decision | The active seat's `wait_for_turn` call returns. The browser receives an SSE event. |
| 5. Submit action | Agent posts an action bound to hand ID and turn token. |
| 6. Validate and apply | Engine accepts one legal action, updates state, appends an event. |
| 7. Advance or settle | Engine deals the next street or settles showdown / last player standing. |
| 8. Publish result | Permitted final information becomes available to history and statistics. |
| 9. Next hand or stop | Continue until hand limit, a stack reaches zero (cash game: sit out or rebuy per config), or admin stops. |

**Timing.** Default decision time is 90 seconds. LLM agents are slow and rate-limited. Simulation mode with scripted bots uses no timeout.

| Failure | Response |
|---|---|
| Agent silent past deadline | Check if legal, otherwise fold. Logged as `timeout`. |
| Malformed request | Structured validation error. Correction allowed within remaining time. |
| Illegal amount | Reject without state change. Return legal range. |
| Duplicate request ID | Return original result. Do not act twice. |
| Stale turn token | HTTP 409 with fresh observation. |
| Service restart | Reload from event log. Table pauses. Admin confirms before play resumes. |
| Three consecutive timeouts | Seat is sat out. Admin can reseat. |

---

## 8. Browser interface

Served by the same FastAPI process. Live updates via Server-Sent Events. No build step.

| Page | Content |
|---|---|
| `/table/{game}` | Seats, names, stacks, bets, pot, board, button, turn indicator, chat feed. Human action controls appear when it is their turn, with legal limits enforced client- and server-side. |
| `/table/{game}/agents` | Per agent: connection state, last request, response latency, timeouts, validation errors. |
| `/hands/{hand}` | Ordered events, shown cards, pots, winners, payouts, and for analysts all hole cards when policy allows. |
| `/admin` | Create games, issue and revoke API keys, assign seats, start and stop tables, set bind address. Shows a warning banner when bound beyond localhost. |
| `/stats` | Leaderboard and per-player statistics with download links. |

The human player authenticates with the same API key mechanism, stored in a browser cookie.

---

## 9. Simulation and evaluation

This section is new in v0.2 and is the reason the core must not depend on the UI.

**Headless runner.** `python -m pokertable.simulate --game config.toml --hands 10000` runs the core directly, with no HTTP, no timeouts, and a recorded seed. Scripted bots and in-process LLM agents can both participate. Ten thousand hands with scripted bots should take seconds.

**Statistics** per player, per game, and across games:

| Metric | Meaning |
|---|---|
| Net chips, bb/100 | The bottom line, normalised by big blinds |
| VPIP, PFR | Voluntarily put money in pot, preflop raise. Style fingerprint. |
| AF | Aggression factor |
| WTSD, W$SD | Went to showdown, won money at showdown |
| Timeouts, invalid actions | Reliability of the agent harness |
| Mean decision latency, tokens used | Cost of the agent |

Every rate metric reports a 95 percent confidence interval. Poker variance is large. Two agents cannot be ranked on a few hundred hands, and the UI should say so rather than show a misleading leaderboard.

---

## 10. Reference agent harness

Ships in Phase 1 as a separate package, `pokertable-agent`. It is what turns "existing agents can connect" into agents actually sitting at the table.

**Loop**

```
while game running:
    obs = GET /wait
    if not my turn: continue
    prompt = render(obs, persona, strategy_notes)
    reply = model(prompt)
    action = parse(reply)          # JSON: {"action": "raise", "amount": 120, "say": "..."}
    POST /actions, retry on network error with same request_id
    if 400 invalid: append error to prompt, one retry
```

**Components**

- Observation-to-prompt renderer with a persona slot ("tight-aggressive", "maniac", "calling station") and optional table-talk style.
- Strict JSON action schema. The parser tolerates fenced code blocks and trailing prose.
- Provider adapters: Anthropic, OpenAI, xAI, Ollama for local models. Each adapter is roughly twenty lines.
- Scripted bots, for testing and baselines: `random`, `always_call`, `tight_aggressive` (simple preflop chart plus pot-odds), `fold_bot`.
- Per-agent cost and latency logging.

An agent built with any other tooling only needs to implement the loop above against the OpenAPI schema.

---

## 11. Delivery phases

**Phase 1 — playable and measurable core**

- Core: PokerKit-backed engine, dealer, event log, SQLite persistence.
- REST: observation, wait, legal actions, actions, chat, hand history, export. OpenAPI served.
- API-key identities with player, observer, admin roles and seat filtering.
- Browser table with SSE, human controls, agent panel, hand inspector, admin page.
- Reference harness with Anthropic adapter and four scripted bots.
- Headless simulation runner with bb/100, VPIP, PFR, and confidence intervals.
- Tests: rules edge cases (split pots, side pots, all-in short stacks), leakage tests across every endpoint, idempotency tests, restart recovery.

**Phase 2 — interoperability and analysis**

- MCP server wrapping the same service functions.
- Analyst role, full statistics endpoint, CSV and text exports.
- Additional provider adapters. Persona library.
- Tournament mode: increasing blinds, elimination, payouts in play chips.
- Multi-table runs for larger-sample agent comparisons.

**Phase 3 — optional**

- WebSocket event stream for clients that want push.
- Deal verification protocol.
- Native or packaged desktop wrapper if ever wanted.

**Acceptance for the first reviewable build**

| Test | Condition |
|---|---|
| Isolation | No seat can obtain another seat's private cards through any endpoint or export, verified by automated tests that call every endpoint with every role. |
| Rules | Scripted edge cases resolve correctly: split pots, multiple side pots, all-in below the minimum raise, heads-up blind order. |
| Interoperability | The reference harness and one independently written client (for example a curl script) complete a game through the published contract. |
| Recovery | Killing the process mid-hand and restarting does not silently alter or continue an ambiguous hand. |
| Audit | Any hand can be replayed from its event log to the same settlement. |
| Simulation | 10,000 hands of scripted bots complete headless with statistics and confidence intervals. |

---

## 12. Decisions register

The ten open questions from v0.1, now answered.

| # | Question | Decision |
|---|---|---|
| 1 | Transport | REST is the only Phase 1 transport. MCP in Phase 2. WebSocket in Phase 3 if ever. |
| 2 | Agent roles | Both. Player first. Observer is trivial once filtering exists. |
| 3 | Where agents run | Anywhere reachable over localhost, LAN, or Tailscale. Service is transport-agnostic. |
| 4 | Turn notification | Long-poll `wait_for_turn`. Agent loops are sequential anyway. |
| 5 | Hole card visibility | Normal mucking rules during play. Per-game policy `reveal_all_after_game` exposes all cards to analysts after the game ends. Default on for research tables. |
| 6 | Deal fairness | Trusted local dealer with `secrets.SystemRandom`. No verification protocol. |
| 7 | Decision time | 90 seconds default, configurable. Check if legal, else fold. Three consecutive timeouts sits the seat out. |
| 8 | Statistics | bb/100, VPIP, PFR, AF, WTSD, W$SD, timeouts, latency, cost. With confidence intervals. |
| 9 | Database | SQLite only. |
| 10 | Table chat | Yes. Stored separately, never affects state, visible in observations, deletable. |

| Item | Position | Status |
|---|---|---|
| Product form | Python service + browser page | Decided |
| Game | Play-money No-Limit Texas Hold'em, cash game first | Decided |
| Engine | PokerKit, not homegrown | Decided |
| Authority | Service owns deal, rules, transitions, settlement | Decided |
| Interfaces | REST baseline, MCP Phase 2 | Decided |
| Persistence | SQLite | Decided |
| Agent DB access | Never | Decided |
| Network | Localhost default, LAN or Tailscale by explicit config | Decided |
| Reference harness | Part of Phase 1 | Decided |
| Headless simulation | Part of Phase 1 | Decided |

---

## 13. Proposed repository layout

```
pokertable/
  pyproject.toml
  config.example.toml
  src/pokertable/
    core/          engine.py (PokerKit wrapper), dealer.py, events.py, settlement.py
    service/       observations.py, actions.py, auth.py, chat.py, stats.py
    api/           app.py, routes_games.py, routes_hands.py, routes_admin.py, sse.py
    db/            models.py, repository.py, migrations/
    web/           templates/, static/
    simulate.py
  src/pokertable_agent/
    harness.py, prompt.py, parse.py
    providers/     anthropic.py, openai.py, xai.py, ollama.py
    bots/          random_bot.py, call_bot.py, tag_bot.py, fold_bot.py
  tests/
    test_rules.py, test_leakage.py, test_idempotency.py, test_recovery.py, test_stats.py
```

## Next document

Once this definition is accepted, the next step is not another document. It is the Phase 1 scaffold: engine wrapper, REST contract, two bots, and a table page that shows a hand being played. The OpenAPI schema generated by that scaffold becomes the formal contract.

*End of definition v0.2*
