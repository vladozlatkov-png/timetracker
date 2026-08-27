'use strict';
/**
 * Realization sync API — Tailscale-only.
 * Auth: static bearer token (TT_BEARER_TOKEN). No login screen.
 * One write path: POST /api/entries (live, corrections, voids, backfills).
 */
const express = require('express');
const { Pool } = require('pg');

const PORT = Number(process.env.PORT || 8787);
const TOKEN = process.env.TT_BEARER_TOKEN || '';
const TZ = 'Europe/Sofia';

if (!TOKEN || TOKEN === 'replace-me-with-a-long-random-token') {
  console.warn('[tt-sync] WARNING: set TT_BEARER_TOKEN to a real secret before production use');
}

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  // Fail fast if misconfigured rather than hang
  connectionTimeoutMillis: 5000,
});

const app = express();
app.use(express.json({ limit: '2mb' }));

function auth(req, res, next) {
  const h = req.headers.authorization || '';
  const ok = TOKEN && h === `Bearer ${TOKEN}`;
  if (!ok) return res.status(401).json({ error: 'unauthorized' });
  next();
}

app.get('/health', (_req, res) => res.json({ ok: true, service: 'tt-sync' }));

app.use('/api', auth);

/** GET /api/streams — picker payload, most recently used first */
app.get('/api/streams', async (_req, res) => {
  try {
    const { rows } = await pool.query(`
      SELECT s.id, s.code, s.name, s.kind, s.billable_default, s.sort_hint,
             s.fee_amount, s.budget_hours, s.billing_model, s.status,
             c.name AS client, c.name_local AS client_local
      FROM tt.stream s
      LEFT JOIN tt.client c ON c.id = s.client_id
      WHERE s.status = 'active'
      ORDER BY s.sort_hint DESC NULLS LAST, s.kind, s.code
    `);
    res.json(rows);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

/**
 * POST /api/entries
 * body: { device_id, entries: [...] }
 * → { accepted: [ids] }
 * Idempotent on id: ON CONFLICT (id) DO NOTHING
 * Never UPDATE an existing row.
 */
app.post('/api/entries', async (req, res) => {
  const device_id = req.body?.device_id;
  const entries = Array.isArray(req.body?.entries) ? req.body.entries : [];
  if (!device_id || !entries.length) {
    return res.status(400).json({ error: 'device_id and entries[] required' });
  }

  const client = await pool.connect();
  const accepted = [];
  try {
    await client.query('BEGIN');
    for (const e of entries) {
      if (!e.id || !e.activity || !e.started_at || !e.ended_at) continue;
      if (new Date(e.ended_at) <= new Date(e.started_at)) continue;
      if ((e.supersedes_id || e.void) && !e.reason) continue;

      // Resolve stream: prefer UUID stream_id; fall back to stream_code (PWA seed ids are not UUIDs)
      let streamId = e.stream_id || null;
      if (streamId && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(streamId)) {
        streamId = null;
      }
      if (!streamId && e.stream_code) {
        const found = await client.query(
          `SELECT id FROM tt.stream WHERE upper(code) = upper($1) LIMIT 1`,
          [e.stream_code]
        );
        streamId = found.rows[0]?.id || null;
      }

      await client.query(
        `INSERT INTO tt.time_entry (
           id, device_id, activity, sub, stream_id, task_notion_id, person,
           billable, started_at, ended_at, note, source, confidence,
           supersedes_id, void, reason, entered_at, synced_at
         ) VALUES (
           $1,$2,$3,$4,$5,$6,COALESCE($7,'vz'),
           COALESCE($8,false),$9,$10,$11,
           COALESCE($12,'pwa'),COALESCE($13,'timed'),
           $14,COALESCE($15,false),$16,
           COALESCE($17::timestamptz, now()), now()
         )
         ON CONFLICT (id) DO NOTHING`,
        [
          e.id,
          device_id,
          e.activity,
          e.sub || null,
          streamId,
          e.task_notion_id || null,
          e.person || 'vz',
          !!e.billable,
          e.started_at,
          e.ended_at,
          e.note || null,
          e.source || 'pwa',
          e.confidence || 'timed',
          e.supersedes_id || null,
          !!e.void,
          e.reason || null,
          e.entered_at || null,
        ]
      );
      accepted.push(e.id); // acknowledge even on conflict — retries are free

      if (streamId) {
        await client.query(
          `UPDATE tt.stream SET sort_hint = now() WHERE id = $1`,
          [streamId]
        );
      }
    }
    await client.query('COMMIT');
    res.json({ accepted });
  } catch (e) {
    await client.query('ROLLBACK');
    console.error(e);
    res.status(500).json({ error: e.message });
  } finally {
    client.release();
  }
});

app.get('/api/realization', async (_req, res) => {
  try {
    const { rows } = await pool.query(`
      SELECT * FROM tt.realization
      ORDER BY effective_hourly ASC NULLS LAST, hours DESC
    `);
    res.json(rows);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/utilization', async (_req, res) => {
  try {
    const { rows } = await pool.query(`SELECT * FROM tt.utilization`);
    res.json(rows);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

/** Current running timer helpers for Shortcuts */
app.get('/api/status', async (req, res) => {
  // Status is client-side; API reports last entry + open streams for Shortcuts copy
  try {
    const { rows } = await pool.query(`
      SELECT e.id, e.activity, e.sub, e.billable, e.started_at, e.ended_at,
             e.duration_s, e.confidence, s.code, s.name AS stream_name
      FROM tt.entry_current e
      LEFT JOIN tt.stream s ON s.id = e.stream_id
      ORDER BY e.started_at DESC
      LIMIT 1
    `);
    res.json({ last_entry: rows[0] || null });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/hours/:code', async (req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT s.code, s.name,
              ROUND(COALESCE(SUM(t.duration_s),0)/3600.0, 2) AS hours_month
       FROM tt.stream s
       LEFT JOIN tt.entry_current t
         ON t.stream_id = s.id
        AND date_trunc('month', t.started_at AT TIME ZONE $2)
            = date_trunc('month', now() AT TIME ZONE $2)
       WHERE upper(s.code) = upper($1)
       GROUP BY s.id`,
      [req.params.code, TZ]
    );
    if (!rows.length) return res.status(404).json({ error: 'stream not found' });
    res.json(rows[0]);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

/**
 * GET /api/day/:date  — YYYY-MM-DD in Europe/Sofia
 * Returns current entries for that local day + computed gaps against working window.
 */
app.get('/api/day/:date', async (req, res) => {
  const date = req.params.date;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    return res.status(400).json({ error: 'date must be YYYY-MM-DD' });
  }
  try {
    const { rows: entries } = await pool.query(
      `SELECT e.*, s.code AS stream_code, s.name AS stream_name, s.kind AS stream_kind
       FROM tt.entry_current e
       LEFT JOIN tt.stream s ON s.id = e.stream_id
       WHERE (e.started_at AT TIME ZONE $2)::date = $1::date
          OR (e.ended_at   AT TIME ZONE $2)::date = $1::date
       ORDER BY e.started_at`,
      [date, TZ]
    );

    const windows = workingWindow(date);
    const gaps = windows ? computeGaps(entries, date, windows) : [];
    const accounted_s = entries.reduce((a, e) => a + Number(e.duration_s || 0), 0);
    const window_s = windows
      ? (parseHM(windows.end) - parseHM(windows.start)) * 60
      : 0;
    const gap_s = gaps.reduce((a, g) => a + g.duration_s, 0);

    res.json({
      date,
      tz: TZ,
      window: windows,
      entries,
      gaps,
      accounted_h: +(accounted_s / 3600).toFixed(2),
      unaccounted_h: +(gap_s / 3600).toFixed(2),
      window_h: +(window_s / 3600).toFixed(2),
    });
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

/** Shortcut-friendly backfill — stamps source/confidence defaults then inserts */
app.post('/api/backfill', async (req, res) => {
  const body = req.body || {};
  const device_id = body.device_id || 'shortcut';
  const id = body.id || require('crypto').randomUUID();
  if (!body.started_at || !body.ended_at) {
    return res.status(400).json({ error: 'started_at and ended_at required' });
  }

  const client = await pool.connect();
  try {
    let streamId = body.stream_id || null;
    if (streamId && !/^[0-9a-f-]{36}$/i.test(streamId)) streamId = null;
    if (!streamId && body.stream_code) {
      const found = await client.query(
        `SELECT id FROM tt.stream WHERE upper(code) = upper($1) LIMIT 1`,
        [body.stream_code]
      );
      streamId = found.rows[0]?.id || null;
    }

    await client.query(
      `INSERT INTO tt.time_entry (
         id, device_id, activity, sub, stream_id, billable, started_at, ended_at,
         note, source, confidence, reason, synced_at
       ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,now())
       ON CONFLICT (id) DO NOTHING`,
      [
        id,
        device_id,
        body.activity || 'billing',
        body.sub || body.stream_code || null,
        streamId,
        !!body.billable,
        body.started_at,
        body.ended_at,
        body.note || null,
        body.source || 'shortcut',
        body.confidence || 'reconstructed',
        body.reason || 'shortcut backfill',
      ]
    );
    if (streamId) {
      await client.query(`UPDATE tt.stream SET sort_hint = now() WHERE id = $1`, [streamId]);
    }
    res.json({ accepted: [id] });
  } catch (e) {
    res.status(500).json({ error: e.message });
  } finally {
    client.release();
  }
});

function parseHM(hm) {
  const [h, m] = hm.split(':').map(Number);
  return h * 60 + m;
}

function workingWindow(isoDate) {
  // Mirror PWA WORK_WINDOWS — Mon–Fri 08–21, Sat 10–16, Sun none
  // isoDate is already a local calendar date (Europe/Sofia)
  const local = new Date(`${isoDate}T12:00:00`);
  const day = local.getDay(); // 0 Sun … 6 Sat
  if (day === 0) return null;
  if (day === 6) return { start: '10:00', end: '16:00' };
  return { start: '08:00', end: '21:00' };
}

function computeGaps(entries, date, window) {
  const startMs = new Date(`${date}T${window.start}:00`).getTime();
  const endMs = new Date(`${date}T${window.end}:00`).getTime();
  const intervals = entries
    .map((e) => ({
      start: Math.max(new Date(e.started_at).getTime(), startMs),
      end: Math.min(new Date(e.ended_at).getTime(), endMs),
    }))
    .filter((i) => i.end > i.start)
    .sort((a, b) => a.start - b.start);

  const gaps = [];
  let cursor = startMs;
  for (const i of intervals) {
    if (i.start > cursor + 60_000) {
      gaps.push({
        start: new Date(cursor).toISOString(),
        end: new Date(i.start).toISOString(),
        duration_s: Math.round((i.start - cursor) / 1000),
      });
    }
    cursor = Math.max(cursor, i.end);
  }
  if (endMs > cursor + 60_000) {
    gaps.push({
      start: new Date(cursor).toISOString(),
      end: new Date(endMs).toISOString(),
      duration_s: Math.round((endMs - cursor) / 1000),
    });
  }
  return gaps;
}

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[tt-sync] listening on :${PORT} (Tailscale perimeter assumed)`);
});
