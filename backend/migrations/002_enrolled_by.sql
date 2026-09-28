-- 002_enrolled_by.sql — pharmacist enrollment ownership (STAGED — do not deploy
-- the enrolled_by code change until this has been run on the live database).
-- Run in Supabase SQL Editor, then deploy the scoped-dashboard release.
ALTER TABLE patient_profiles ADD COLUMN IF NOT EXISTS enrolled_by UUID REFERENCES users(id);

-- New enrollments record the enrolling pharmacist directly. Rows enrolled before
-- this migration have no owner and will not appear in any pharmacist's worklist
-- until re-enrolled (acceptable for the current test population).
