'use strict';
/** Apply SQL migrations from ../sql against DATABASE_URL */
const fs = require('fs');
const path = require('path');
const { Pool } = require('pg');

async function main() {
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });
  const dir = path.join(__dirname, '..', 'sql');
  const files = fs.readdirSync(dir).filter((f) => /^\d+_.*\.sql$/.test(f) && !f.includes('rollback')).sort();
  for (const f of files) {
    const sql = fs.readFileSync(path.join(dir, f), 'utf8');
    console.log('Applying', f);
    await pool.query(sql);
  }
  console.log('Done.');
  await pool.end();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
