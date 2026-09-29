-- 003_consent_timestamp_nullable.sql — G10 consent-timestamp semantics (STAGED).
-- Run on the live database BEFORE deploying the G10 code change, then confirm.
-- After this runs, enrollment writes NULL until the patient attests consent
-- on-device, and consent_timestamp then means exactly "when consent occurred".
ALTER TABLE patient_profiles ALTER COLUMN consent_timestamp DROP NOT NULL;
