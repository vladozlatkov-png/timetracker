-- Seed clients, client engagements, and internal/admin streams.
-- Fees: fill fee_amount from Договори_одит_2024 (Google Drive) — all EUR.
-- This seed leaves fee_amount NULL so a missing sheet never invents a number.
-- Idempotent: safe to re-run.

INSERT INTO tt.client (name, name_local)
SELECT v.name, v.name_local
FROM (VALUES
  ('Scorpio Oil Transport OOD', NULL::text),
  ('Global Exchange OOD', NULL),
  ('Kumer OOD', 'Кумер ООД'),
  ('Fashion Icon OOD', 'Фешън Айкон ООД'),
  ('MBAL Samokov EOOD', 'МБАЛ Самоков ЕООД'),
  ('B2B EOOD', 'Би Ту Би ЕООД')
) AS v(name, name_local)
WHERE NOT EXISTS (SELECT 1 FROM tt.client c WHERE c.name = v.name);

INSERT INTO tt.stream (kind, client_id, name, code, fiscal_year, fee_currency, billing_model, billable_default, status, sort_hint)
SELECT
  'client',
  c.id,
  v.engagement,
  v.code,
  2025,
  'EUR',
  'fixed',
  true,
  'active',
  now()
FROM (VALUES
  ('Scorpio Oil Transport OOD', 'Statutory Audit FY2025', 'SCORPIO-25'),
  ('Global Exchange OOD',       'Statutory Audit FY2025', 'GLOBAL-25'),
  ('Kumer OOD',                 'Statutory Audit FY2025', 'KUMER-25'),
  ('Fashion Icon OOD',          'Statutory Audit FY2025', 'FASHION-25'),
  ('MBAL Samokov EOOD',         'Statutory Audit FY2025', 'SAMOKOV-25'),
  ('B2B EOOD',                  'Statutory Audit FY2025', 'B2B-25')
) AS v(client_name, engagement, code)
JOIN tt.client c ON c.name = v.client_name
WHERE NOT EXISTS (SELECT 1 FROM tt.stream s WHERE s.code = v.code);

INSERT INTO tt.stream (kind, client_id, name, code, fee_currency, billing_model, billable_default, status, sort_hint)
SELECT v.kind, NULL, v.name, v.code, 'EUR', 'fixed', false, 'active', now()
FROM (VALUES
  ('internal', 'Audit OS / ERPNext',              'DEV-AUDITOS'),
  ('internal', 'Realization app',                 'DEV-REAL'),
  ('internal', 'Home lab & infrastructure',       'DEV-HOMELAB'),
  ('admin',    'Easy Ventures administration, banking, filings', 'EV-ADMIN'),
  ('admin',    'Business development, leads, proposals',         'BD')
) AS v(kind, name, code)
WHERE NOT EXISTS (SELECT 1 FROM tt.stream s WHERE s.code = v.code);

-- After loading Договори_одит_2024, set fees (EUR only):
-- UPDATE tt.stream SET fee_amount = <EUR> WHERE code = 'SCORPIO-25';
-- UPDATE tt.stream SET fee_amount = <EUR> WHERE code = 'GLOBAL-25';
-- UPDATE tt.stream SET fee_amount = <EUR> WHERE code = 'KUMER-25';
-- UPDATE tt.stream SET fee_amount = <EUR> WHERE code = 'FASHION-25';
-- UPDATE tt.stream SET fee_amount = <EUR> WHERE code = 'SAMOKOV-25';
-- UPDATE tt.stream SET fee_amount = <EUR> WHERE code = 'B2B-25';
