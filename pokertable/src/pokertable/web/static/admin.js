(function () {
  const $ = (id) => document.getElementById(id);
  const post = (url, body) => fetch(url, { method: body ? 'POST' : 'POST', headers: { 'content-type': 'application/json' }, body: body ? JSON.stringify(body) : undefined }).then(async (r) => [r.ok, await r.json()]);
  $('create-game').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target), body = {};
    for (const [k, v] of f.entries()) body[k] = v;
    for (const k of ['small_blind', 'big_blind', 'starting_stack', 'max_seats', 'hand_limit']) body[k] = parseInt(body[k], 10);
    for (const k of ['decision_seconds', 'hand_pause_seconds']) body[k] = parseFloat(body[k]);
    for (const k of ['reveal_all_after_game', 'open_join', 'auto_rebuy']) body[k] = f.get(k) === 'on';
    const [ok, j] = await post('/v1/admin/games', body);
    if (ok) location.reload(); else alert((j.detail && j.detail.message) || JSON.stringify(j));
  });
  $('seat-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const [ok, j] = await post(`/v1/admin/games/${f.get('game_id')}/seats`, { identity_id: f.get('identity_id'), seat: f.get('seat') ? +f.get('seat') : null });
    if (ok) location.reload(); else alert((j.detail && j.detail.message) || JSON.stringify(j));
  });
  $('create-identity').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const [ok, j] = await post('/v1/admin/identities', { name: f.get('name'), role: f.get('role') });
    const pre = $('new-key'); pre.classList.remove('hidden');
    pre.textContent = ok ? `Identity ${j.id} (${j.role}) created.\nAPI key (shown once): ${j.api_key}` : ((j.detail && j.detail.message) || JSON.stringify(j));
  });
  for (const b of document.querySelectorAll('button[data-cmd]')) b.addEventListener('click', async () => { const [ok, j] = await post(`/v1/admin/games/${b.dataset.game}/${b.dataset.cmd}`); if (ok) location.reload(); else alert((j.detail && j.detail.message) || JSON.stringify(j)); });
  for (const b of document.querySelectorAll('button[data-revoke]')) b.addEventListener('click', async () => { if (!confirm(`Revoke ${b.dataset.revoke}?`)) return; await fetch(`/v1/admin/identities/${b.dataset.revoke}`, { method: 'DELETE' }); location.reload(); });
})();
