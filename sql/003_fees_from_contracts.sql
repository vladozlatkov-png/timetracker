-- Template: set engagement fees from Договори_одит_2024 (all EUR).
-- Copy amounts from the sheet; do not invent them.

BEGIN;

UPDATE tt.stream SET fee_amount = NULL WHERE code = 'SCORPIO-25';  -- TODO EUR
UPDATE tt.stream SET fee_amount = NULL WHERE code = 'GLOBAL-25';   -- TODO EUR
UPDATE tt.stream SET fee_amount = NULL WHERE code = 'KUMER-25';    -- TODO EUR
UPDATE tt.stream SET fee_amount = NULL WHERE code = 'FASHION-25';  -- TODO EUR
UPDATE tt.stream SET fee_amount = NULL WHERE code = 'SAMOKOV-25';  -- TODO EUR
UPDATE tt.stream SET fee_amount = NULL WHERE code = 'B2B-25';      -- TODO EUR

-- Optional budget hours (his own estimate, for burn %):
-- UPDATE tt.stream SET budget_hours = 40 WHERE code = 'SCORPIO-25';

COMMIT;
