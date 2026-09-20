(function () {
  const G = window.GAME, ME = window.ME;
  const $ = (id) => document.getElementById(id);
  let obs = null, deadline = null;

  function card(c) {
    if (!c) return '<span class="cardface back">??</span>';
    const suit = c[1], sym = { s: '♠', h: '♥', d: '♦', c: '♣' }[suit] || suit;
    const red = suit === 'h' || suit === 'd';
    return `<span class="cardface ${red ? 'r' : ''}">${c[0]}${sym}</span>`;
  }

  function seatPos(i, n) {
    const a = (Math.PI * 2 * i) / n + Math.PI / 2; // start at bottom
    return { left: 50 + 42 * Math.cos(a), top: 50 + 40 * Math.sin(a) };
  }

  function render(o) {
    obs = o;
    $('status').textContent = statusLine(o);
    $('board').innerHTML = (o.board || []).map(card).join('') + '<span style="width:0"></span>'.repeat(0);
    $('pot').textContent = o.pot ? `Pot ${o.pot}` : '';
    const seats = o.seats || [], n = Math.max(seats.length, 1);
    const mine = o.my_seat;
    const rotated = seats.slice();
    const idx = seats.findIndex((s) => s.seat === mine);
    const order = idx >= 0 ? rotated.slice(idx).concat(rotated.slice(0, idx)) : rotated;
    $('seats').innerHTML = order.map((s, i) => {
      const p = seatPos(i, n);
      const cls = ['seat', s.status === 'folded' ? 'folded' : '', s.seat === o.acting_seat ? 'acting' : '', s.seat === mine ? 'me' : ''].join(' ');
      let cards = '';
      if (s.seat === mine && o.hole_cards) cards = o.hole_cards.map(card).join('');
      else if (s.shown_cards) cards = s.shown_cards.map(card).join('');
      else if (s.status === 'active' || s.status === 'all_in') cards = card() + card();
      return `<div class="${cls}" style="left:${p.left}%;top:${p.top}%">
        <div class="name">${esc(s.name)}${s.seat === o.button_seat ? '<span class="btn">D</span>' : ''} <span class="muted">${s.position || ''}</span></div>
        <div class="stack">${s.stack}${s.status === 'all_in' ? ' all-in' : ''}${s.sitting_out ? ' (out)' : ''}</div>
        <div class="bet">${s.bet ? 'bet ' + s.bet : ''}</div><div>${cards}</div></div>`;
    }).join('');
    $('chat').innerHTML = (o.recent_chat || []).map((m) => `<div><b>${esc(m.name)}</b>: ${esc(m.text)}</div>`).join('');
    $('actions').innerHTML = (o.hand_actions || []).map((a) => `<li>seat ${a.seat} ${a.action}${a.amount ? ' ' + a.amount : ''} <span class="muted">${a.phase}</span></li>`).join('');
    $('last').textContent = o.last_hand ? `Last hand #${o.last_hand.hand_id}: board ${o.last_hand.board.join(' ')}, winners ${o.last_hand.winners.join(', ')}` : '';
    const ctl = $('controls');
    if (o.my_turn) {
      ctl.classList.remove('hidden');
      $('hole').innerHTML = (o.hole_cards || []).map(card).join('');
      const la = o.legal_actions || [];
      for (const b of ctl.querySelectorAll('button[data-action]')) {
        const a = b.dataset.action;
        b.disabled = !(la.includes(a) || (a === 'raise' && la.includes('bet')));
        if (a === 'raise') b.textContent = la.includes('bet') ? 'Bet' : 'Raise to';
      }
      $('call-amt').textContent = o.amount_to_call || '';
      const r = $('raise-amt'); r.min = o.min_raise_to || 0; r.max = o.max_raise_to || 0; if (!r.value || +r.value < r.min) r.value = o.min_raise_to || 0;
      deadline = Date.now() + (o.seconds_left || 0) * 1000;
    } else { ctl.classList.add('hidden'); deadline = null; }
  }

  function statusLine(o) {
    if (o.game_status === 'waiting') return 'Waiting for the administrator to start the table.';
    if (o.game_status === 'paused') return 'Paused. An administrator must resume.';
    if (o.game_status === 'finished') return 'Table finished.';
    if (o.next_hand_in != null) return `Next hand in ${o.next_hand_in}s`;
    const who = (o.seats || []).find((s) => s.seat === o.acting_seat);
    return `Hand ${o.hand_id} · ${o.phase} · ${who ? who.name + ' to act' : ''}`;
  }

  function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

  async function act(action) {
    const body = { request_id: 'ui-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8), hand_id: obs.hand_id, turn_token: obs.turn_token, action };
    if (action === 'raise') { body.action = (obs.legal_actions || []).includes('bet') ? 'bet' : 'raise'; body.amount = +$('raise-amt').value; }
    const r = await fetch(`/v1/games/${G}/actions`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-connector': 'browser' }, body: JSON.stringify(body) });
    const j = await r.json();
    $('err').textContent = r.ok ? '' : (j.detail && j.detail.message) || JSON.stringify(j);
  }

  for (const b of document.querySelectorAll('#controls button[data-action]')) b.addEventListener('click', () => act(b.dataset.action));
  const join = $('join'); if (join) join.addEventListener('click', async () => { await fetch(`/v1/games/${G}/seats/join`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ connector: 'browser' }) }); location.reload(); });
  const cf = $('chat-form'); if (cf) cf.addEventListener('submit', async (e) => { e.preventDefault(); const t = $('chat-text').value.trim(); if (!t) return; $('chat-text').value = ''; await fetch(`/v1/games/${G}/chat`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text: t }) }); });
  for (const b of document.querySelectorAll('button[data-admin]')) b.addEventListener('click', async () => { await fetch(`/v1/admin/games/${G}/${b.dataset.admin}`, { method: 'POST' }); });
  setInterval(() => { if (deadline) $('timer').textContent = Math.max(0, Math.ceil((deadline - Date.now()) / 1000)) + 's'; }, 250);

  const es = new EventSource(`/v1/games/${G}/stream`);
  es.addEventListener('state', (e) => render(JSON.parse(e.data)));
  es.onerror = () => { $('status').textContent = 'Connection lost, retrying…'; };
})();
