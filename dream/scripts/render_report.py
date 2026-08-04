#!/usr/bin/env python3
"""
Render a dream proposals JSON file to a self-contained HTML report.

The report is rendered rather than hand-written so that every night's output has
the same shape, and so the model spends its tokens on analysis instead of markup.

Usage:
    render_report.py --proposals proposals-2026-08-04.json --out dream-2026-08-04.html
"""

import argparse
import html
import json
import sys
from pathlib import Path

CATEGORY_META = {
    "correction": ("Corrections", "Things you told me I got wrong."),
    "preference": ("Preferences", "Standing instructions, not one-off requests."),
    "fact": ("New facts", "Durable things worth not rediscovering."),
    "duplicate": ("Duplicates", "The same thing recorded twice."),
    "stale": ("Stale or wrong", "Memory contradicted by what actually happened."),
}
CATEGORY_ORDER = ["correction", "preference", "fact", "duplicate", "stale"]
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --bg:#fbfaf8; --panel:#fff; --ink:#1b1a17; --muted:#6b665e; --line:#e6e2da;
  --accent:#8a5a2b; --accent-soft:#f3ece2; --quote:#f7f4ef;
  --hi:#b4472b; --ok:#3f6b4a;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#16151a; --panel:#1e1d24; --ink:#eceaf2; --muted:#9d97a8; --line:#302e39;
    --accent:#d8a366; --accent-soft:#2a2620; --quote:#232128;
    --hi:#e08a6d; --ok:#7fb08c;
  }
}
:root[data-theme=light]{
  --bg:#fbfaf8; --panel:#fff; --ink:#1b1a17; --muted:#6b665e; --line:#e6e2da;
  --accent:#8a5a2b; --accent-soft:#f3ece2; --quote:#f7f4ef; --hi:#b4472b; --ok:#3f6b4a;
}
:root[data-theme=dark]{
  --bg:#16151a; --panel:#1e1d24; --ink:#eceaf2; --muted:#9d97a8; --line:#302e39;
  --accent:#d8a366; --accent-soft:#2a2620; --quote:#232128; --hi:#e08a6d; --ok:#7fb08c;
}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.6 ui-serif,Georgia,"Iowan Old Style",serif;padding:2.5rem 1.25rem 5rem}
.wrap{max-width:56rem;margin:0 auto}
header{border-bottom:2px solid var(--line);padding-bottom:1.25rem;margin-bottom:1.75rem}
h1{font-size:1.9rem;margin:0 0 .3rem;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:.9rem;font-family:ui-sans-serif,system-ui,sans-serif}
.stats{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:1rem}
.stat{background:var(--accent-soft);border:1px solid var(--line);border-radius:99px;
  padding:.25rem .75rem;font:600 .78rem ui-sans-serif,system-ui,sans-serif;color:var(--accent)}
.summary{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:6px;padding:1rem 1.15rem;margin-bottom:2rem;font-style:italic}
h2{font-size:1.15rem;margin:2.25rem 0 .3rem;letter-spacing:-.01em}
h2 .count{color:var(--muted);font-weight:400;font-size:.9rem}
.cat-note{color:var(--muted);font-size:.86rem;margin:0 0 1rem;
  font-family:ui-sans-serif,system-ui,sans-serif}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;
  padding:1rem 1.15rem;margin-bottom:.85rem}
.card-top{display:flex;gap:.7rem;align-items:flex-start}
.card input[type=checkbox]{margin-top:.35rem;width:1.05rem;height:1.05rem;
  accent-color:var(--accent);flex:none;cursor:pointer}
.idnum{font:700 .82rem ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--accent);
  background:var(--accent-soft);border-radius:4px;padding:.1rem .45rem;flex:none;margin-top:.2rem}
.body{flex:1;min-width:0}
.title{font-weight:600;margin:0 0 .35rem}
.tags{display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.5rem}
.tag{font:600 .68rem ui-sans-serif,system-ui,sans-serif;text-transform:uppercase;
  letter-spacing:.04em;color:var(--muted);border:1px solid var(--line);
  border-radius:3px;padding:.08rem .38rem}
.tag.high{color:var(--ok);border-color:var(--ok)}
.tag.low{color:var(--hi);border-color:var(--hi)}
.change{font:.85rem/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--quote);
  border:1px solid var(--line);border-radius:5px;padding:.6rem .75rem;margin:.5rem 0;
  overflow-x:auto;white-space:pre-wrap;word-break:break-word}
blockquote{margin:.5rem 0 .35rem;padding:.35rem 0 .35rem .85rem;
  border-left:2px solid var(--accent);color:var(--ink);font-size:.92rem}
blockquote .src{display:block;margin-top:.3rem;color:var(--muted);font-size:.76rem;
  font-family:ui-sans-serif,system-ui,sans-serif;font-style:normal}
.rationale{color:var(--muted);font-size:.86rem;margin-top:.4rem;
  font-family:ui-sans-serif,system-ui,sans-serif}
.applied{background:var(--panel);border:1px dashed var(--line);border-radius:6px;
  padding:.7rem .9rem;margin-bottom:.5rem;font-size:.9rem}
.empty{color:var(--muted);font-style:italic;padding:1.5rem 0}
.warn{background:var(--accent-soft);border:1px solid var(--hi);border-radius:6px;
  padding:.7rem .9rem;margin-bottom:1.5rem;font-size:.9rem;
  font-family:ui-sans-serif,system-ui,sans-serif}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--panel);
  border-top:1px solid var(--line);padding:.7rem 1.25rem;display:flex;gap:.8rem;
  align-items:center;justify-content:center;flex-wrap:wrap;
  font-family:ui-sans-serif,system-ui,sans-serif;font-size:.87rem}
.bar code{background:var(--quote);border:1px solid var(--line);border-radius:4px;
  padding:.28rem .55rem;font:.85rem ui-monospace,Menlo,monospace;
  max-width:60vw;overflow-x:auto;white-space:nowrap}
button{font:600 .85rem ui-sans-serif,system-ui,sans-serif;background:var(--accent);
  color:var(--bg);border:0;border-radius:5px;padding:.4rem .85rem;cursor:pointer}
button.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent)}
@media print{.bar{display:none}body{padding-bottom:2rem}}
"""

JS = """
function refresh(){
  const ids=[...document.querySelectorAll('.pick:checked')].map(c=>c.dataset.id);
  document.getElementById('cmd').textContent =
    ids.length ? 'apply dream proposals '+ids.join(', ') : 'select proposals to approve…';
  document.getElementById('n').textContent = ids.length;
}
document.addEventListener('change',e=>{if(e.target.classList.contains('pick'))refresh()});
function all(v){document.querySelectorAll('.pick').forEach(c=>c.checked=v);refresh()}
function copy(){
  const t=document.getElementById('cmd').textContent;
  if(t.startsWith('select'))return;
  navigator.clipboard.writeText(t).then(()=>{
    const b=document.getElementById('cp'),o=b.textContent;
    b.textContent='Copied';setTimeout(()=>b.textContent=o,1200);
  });
}
refresh();
"""


def esc(value):
    return html.escape(str(value if value is not None else ""))


def render_evidence(items):
    if not items:
        return ""
    out = []
    for ev in items:
        if not isinstance(ev, dict):
            continue
        src_bits = [
            b
            for b in (ev.get("project"), ev.get("session_id"), ev.get("ts"))
            if b
        ]
        src = " · ".join(esc(b) for b in src_bits)
        out.append(
            f'<blockquote>“{esc(ev.get("quote", ""))}”'
            + (f'<span class="src">{src}</span>' if src else "")
            + "</blockquote>"
        )
    return "".join(out)


def render_proposal(p):
    pid = esc(p.get("id"))
    conf = str(p.get("confidence", "medium")).lower()
    conf_class = conf if conf in ("high", "low") else ""
    tags = [
        f'<span class="tag {conf_class}">{esc(conf)} confidence</span>',
        f'<span class="tag">{esc(p.get("action", "add"))}</span>',
        f'<span class="tag">{esc(p.get("target", ""))}</span>',
    ]
    change = p.get("change", "")
    rationale = p.get("rationale", "")
    return f"""<div class="card"><div class="card-top">
<input type="checkbox" class="pick" data-id="{pid}" id="p{pid}">
<span class="idnum">{pid}</span>
<div class="body">
<label class="title" for="p{pid}">{esc(p.get("summary", ""))}</label>
<div class="tags">{"".join(tags)}</div>
{f'<div class="change">{esc(change)}</div>' if change else ""}
{render_evidence(p.get("evidence"))}
{f'<div class="rationale">{esc(rationale)}</div>' if rationale else ""}
</div></div></div>"""


def build(data):
    proposals = data.get("proposals") or []
    applied = data.get("auto_applied") or []
    date = esc(data.get("date", "unknown"))

    by_cat = {}
    for p in proposals:
        by_cat.setdefault(str(p.get("category", "fact")).lower(), []).append(p)
    for bucket in by_cat.values():
        bucket.sort(
            key=lambda p: CONFIDENCE_ORDER.get(
                str(p.get("confidence", "medium")).lower(), 1
            )
        )

    stats = [
        f'<span class="stat">{len(proposals)} proposal{"s" if len(proposals) != 1 else ""}</span>',
        f'<span class="stat">{esc(data.get("sessions_reviewed", 0))} sessions</span>',
    ]
    if applied:
        stats.append(f'<span class="stat">{len(applied)} auto-applied</span>')
    for cat in CATEGORY_ORDER:
        if by_cat.get(cat):
            stats.append(
                f'<span class="stat">{len(by_cat[cat])} {esc(CATEGORY_META[cat][0].lower())}</span>'
            )

    parts = [
        '<div class="wrap"><header>',
        f"<h1>Dream · {date}</h1>",
        f'<div class="sub">{esc(", ".join(data.get("projects") or [])) or "no projects recorded"}'
        f' · {esc(data.get("window_hours", 24))}h window</div>',
        f'<div class="stats">{"".join(stats)}</div>',
        "</header>",
    ]

    if data.get("vault_reachable") is False:
        parts.append(
            '<div class="warn"><strong>Vault unreachable.</strong> The NAS was not '
            "mounted during this run, so only <code>~/.claude/CLAUDE.md</code> was "
            "compared. Vault-side duplicates and stale notes were not checked.</div>"
        )

    if data.get("day_summary"):
        parts.append(f'<div class="summary">{esc(data["day_summary"])}</div>')

    if applied:
        parts.append('<h2>Auto-applied <span class="count">— already done</span></h2>')
        parts.append(
            '<p class="cat-note">Trivially safe fixes applied without asking. '
            "A backup was taken first.</p>"
        )
        for item in applied:
            parts.append(
                f'<div class="applied"><span class="idnum">{esc(item.get("id", "A"))}</span> '
                f'{esc(item.get("what", ""))} <span class="sub">— {esc(item.get("target", ""))}</span></div>'
            )

    if not proposals:
        parts.append(
            '<div class="empty">Nothing to propose. Either it was a quiet day, or '
            "memory already reflects it.</div>"
        )
    else:
        for cat in CATEGORY_ORDER:
            bucket = by_cat.get(cat)
            if not bucket:
                continue
            label, note = CATEGORY_META[cat]
            parts.append(f'<h2>{label} <span class="count">— {len(bucket)}</span></h2>')
            parts.append(f'<p class="cat-note">{note}</p>')
            parts.extend(render_proposal(p) for p in bucket)

        leftovers = set(by_cat) - set(CATEGORY_ORDER)
        for cat in sorted(leftovers):
            parts.append(f'<h2>{esc(cat)} <span class="count">— {len(by_cat[cat])}</span></h2>')
            parts.extend(render_proposal(p) for p in by_cat[cat])

    parts.append("</div>")

    if proposals:
        parts.append(
            '<div class="bar"><button class="ghost" onclick="all(true)">All</button>'
            '<button class="ghost" onclick="all(false)">None</button>'
            '<span><strong id="n">0</strong> selected</span>'
            '<code id="cmd"></code>'
            '<button id="cp" onclick="copy()">Copy</button></div>'
        )

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Dream · {date}</title><style>{CSS}</style></head><body>"
        + "".join(parts)
        + f"<script>{JS}</script></body></html>"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposals", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    src = Path(args.proposals).expanduser()
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"error: no proposals file at {src}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"error: {src} is not valid JSON: {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build(data), encoding="utf-8")
    print(f"wrote {out_path} ({len(data.get('proposals') or [])} proposals)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
