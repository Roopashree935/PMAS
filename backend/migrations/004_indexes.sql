-- Migration 004: hot-path foreign-key indexes (issue #32)
-- Run on the live PostgreSQL (Supabase SQL editor) BEFORE deploying the code
-- that relies on them — same sequencing rule as migrations 002 and 003.
-- All statements are IF NOT EXISTS, so re-running is safe.

CREATE INDEX IF NOT EXISTS idx_adherence_patient_date
    ON adherence_records (patient_id, dose_date);

CREATE INDEX IF NOT EXISTS idx_symptom_patient_date
    ON symptom_telemetry (patient_id, log_date);

CREATE INDEX IF NOT EXISTS idx_medplans_patient
    ON medication_plans (patient_id);

CREATE INDEX IF NOT EXISTS idx_profiles_enrolled_by
    ON patient_profiles (enrolled_by);
