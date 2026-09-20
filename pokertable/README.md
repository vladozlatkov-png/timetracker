# Independent AI Poker Table

A Python service that hosts play-money No-Limit Texas Hold'em between a human and independently running AI agents. The service is the dealer, the rules authority and the system of record. Agents connect over REST. Humans use a browser page.

This is the Phase 1 scaffold described in [`../docs/poker-table-definition-v0.2.md`](../docs/poker-table-definition-v0.2.md).

## What is here

| Package | Purpose |
|---|---|
| `pokertable.core` | Dealer (OS CSPRNG) and one-hand engine wrapping [PokerKit](https://github.com/uoftcprg/pokerkit): blinds, side pots, all-ins, showdown, replayable event log |
| `pokertable.service` | Table: seats, hand loop, per-seat filtered observations, idempotent actions, turn tokens, timeouts, chat, statistics |
| `pokertable.db` | SQLite persistence: identities, game snapshots, completed hands, per-seat results, chat, request log |
| `pokertable.api` | FastAPI REST contract, API-key auth, long-poll `wait`, Server-Sent Events, admin endpoints, exports, browser pages |
| `pokertable.simulate` | Headless runner: thousands of hands in seconds with in-process agents |
| `pokertable_agent` | Reference harness: REST loop, prompt renderer, reply parser, scripted bots, Anthropic adapter |

## Quickstart

```bash
cd pokertable
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp config.example.toml config.toml      # edit the API keys
pokertable                              # http://127.0.0.1:8420
```

Open http://127.0.0.1:8420/admin, sign in with the admin key, create a table. Then seat some agents from other terminals:

```bash
pokertable-agent --key change-me-tag-key  --game table-1 --bot tag
pokertable-agent --key change-me-call-key --game table-1 --bot call
ANTHROPIC_API_KEY=... pokertable-agent --key change-me-claude-key --game table-1 --llm anthropic --persona lag -v
```

Press **start** on the admin page or the table page. Sign in on the table page with a player key to take a seat yourself.

### Headless simulation

```bash
pokertable-simulate --hands 10000 --seed 1 --bots tag,call,random,fold
```

Prints net chips, bb/100 with a 95% confidence interval, VPIP, PFR, AF, WTSD and W$SD per bot.

### Tests

```bash
pytest
```

Covers rules edge cases (split pots, side pots, short all-ins, heads-up order, replay), information leakage across every role and endpoint, idempotency and turn tokens, timeouts, restart recovery, statistics math, and the agent parser.

## REST contract

All under `/v1`, bearer API key, OpenAPI at `/docs`.

| Capability | Endpoint |
|---|---|
| Who am I | `GET /me` |
| Discover games | `GET /games` |
| Take a seat | `POST /games/{game}/seats/join` |
| Read my filtered observation | `GET /games/{game}/observation` |
| Block until it is my turn | `GET /games/{game}/wait?timeout=30` |
| Legal actions | `GET /games/{game}/legal-actions` |
| Act | `POST /games/{game}/actions` `{request_id, hand_id, turn_token, action, amount?}` |
| Table talk | `POST /games/{game}/chat` |
| Completed hands | `GET /games/{game}/hands`, `GET /games/{game}/hands/{n}` |
| Statistics | `GET /games/{game}/stats`, `GET /players/{id}/stats` |
| Export | `GET /games/{game}/export?format=json|csv|txt` |
| Live events | `GET /games/{game}/stream` (SSE) |
| Admin | `POST /admin/games`, `POST /admin/games/{game}/{start|pause|resume|stop|clear-chat}`, `POST /admin/games/{game}/seats`, `POST /admin/identities` |

An agent loop is: `wait` → decide → `POST actions` with a fresh `request_id` → repeat. Repeating a `request_id` returns the original result and never acts twice. A wrong `turn_token` returns 409 with a fresh observation. An illegal action returns 400 with the legal range and the seconds left.

## Trust model

- Every response is built for one authenticated identity. Players see their own hole cards only. Observers, analysts and admins see public state only during a hand.
- After a game finishes, analysts and admins can see all hole cards of its hands if the table was created with `reveal_all_after_game` (default on, for research).
- Agents never get database access. Keys are stored hashed. The live hand is never persisted, so a crash cannot leak it and a restart cannot silently continue it: the table comes back **paused** for an administrator to resume.
- The service binds to localhost. Set `bind = "0.0.0.0"` in `config.toml` for LAN or Tailscale access. The UI shows a banner when exposed.

## Writing your own agent

Implement `decide(observation, error=None) -> Decision` and hand it to `pokertable_agent.harness.play`, or speak the REST contract directly from any language. `pokertable_agent/prompt.py` is the single place that turns an observation into a prompt, so every model sees the same table.
