/* ═══════════════════════════════════════════════════════════════
   PMAS — Fixed clinical date keys (Asia/Kolkata, UTC+05:30)

   Dose dates, streaks, study days and day-scoped summaries are keyed
   by the clinical calendar, NOT the device clock's UTC: Date.toISOString()
   returns UTC, so a dose taken between 00:00 and 05:30 IST would be
   attributed to the previous day (issue #28).

   The backend uses the same fixed timezone (backend/main.py: CLINICAL_TZ).
   India has no DST, so a constant offset is exact.
   ═══════════════════════════════════════════════════════════════ */
const CLINICAL_TZ_OFFSET_MS = 5.5 * 60 * 60 * 1000;

function clinicalDateKey(d) {
  return new Date((d || new Date()).getTime() + CLINICAL_TZ_OFFSET_MS)
    .toISOString().split('T')[0];
}
