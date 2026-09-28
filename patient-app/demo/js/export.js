/* ═══════════════════════════════════════════════════════════════
   PMAS — Export Module
   Two completely separate exports:
   1. De-identified Research Export (Study ID + Study Day, no raw dates)
   2. Patient Health Summary (printable HTML → PDF)
   These two MUST NEVER be mixed.
   ═══════════════════════════════════════════════════════════════ */

/* ── 1. DE-IDENTIFIED RESEARCH EXPORT ────────────────────── */
/* Strictly no PII: no name, phone, DOB, emergency contact,
   doctor names, or free-text notes.
   Uses Study ID + Study Day instead of raw dates. */
function exportResearchData() {
  const meds  = DB.get('medications')  || [];
  const syms  = DB.get('symptoms')     || [];
  const appts = DB.get('appointments') || [];
  const cons  = DB.get('consent')      || {};
  const studyMeta = StudyID.get();
  const todayStats = Adherence.getTodayStats();
  const weeklyStats = Adherence.getWeeklyStats();

  // All adherence records, with dates converted to study days
  const adherenceRecords = Adherence.getAll().map(a => ({
    study_day: StudyID.dateToStudyDay(a.date),
    slot: a.slot,
    status: a.status
    // No med_id by name — use index reference only
  }));

  const exportPayload = {
    study:           'PMAS-RESEARCH',
    study_id:        studyMeta.study_id,
    consent_ver:     cons.version   || null,
    lang_used:       cons.language  || lang,
    study_day_at_export: StudyID.getStudyDay(),

    /* Adherence variables — PRIMARY OUTCOME */
    adherence: {
      today_pct:         todayStats.adherencePct,
      today_taken:       todayStats.takenCount,
      today_scheduled:   todayStats.totalScheduled,
      weekly_pct:        weeklyStats.adherencePct,
      weekly_taken:      weeklyStats.takenCount,
      weekly_scheduled:  weeklyStats.totalScheduled,
      days_recorded:     weeklyStats.daysWithRecords,
      total_records:     adherenceRecords.length,
      records:           adherenceRecords  // study_day instead of raw date
    },

    /* Medication patterns — no names, no doses, no notes */
    medications: {
      total_count: meds.length,
      active_count: meds.filter(m => {
        const today = new Date().toISOString().split('T')[0];
        return (!m.end_date || m.end_date >= today);
      }).length,
      schedule_patterns: meds.map(m => ({
        morning:   m.morning   ? 1 : 0,
        afternoon: m.afternoon ? 1 : 0,
        night:     m.night     ? 1 : 0,
        has_times: (m.morning_time||m.afternoon_time||m.night_time) ? 1 : 0,
        duration_days: (m.start_date && m.end_date)
          ? Math.round((new Date(m.end_date)-new Date(m.start_date))/(86400000))
          : null
        // No medication names, no dose values, no notes
      }))
    },

    /* Symptom variables — study day instead of raw date */
    symptoms: {
      total_logs: syms.length,
      entries: syms.map(s => ({
        study_day:    StudyID.dateToStudyDay(s.date),
        pain_score:   s.pain    ?? null,
        temp_c:       s.temp    ?? null,
        weight_kg:    s.weight  ?? null,
        bp_sys:       s.bp_sys  ?? null,
        bp_dia:       s.bp_dia  ?? null,
        has_symptoms:    s.symptoms     ? 1 : 0,
        has_side_effects: s.side_effects ? 1 : 0
        // Notes excluded — may contain identifiers
      })),
      avg_pain: syms.length
        ? +(syms.reduce((a,s)=>a+(s.pain||0),0)/syms.length).toFixed(2)
        : null,
      high_pain_events: syms.filter(s => s.pain >= 8).length,
      high_bp_events:   syms.filter(s => s.bp_sys >= 180).length
    },

    /* Appointments — count only, no doctor names or notes */
    appointments: {
      total_count: appts.length
    },

    /* Data governance — design alignment, not legal certification */
    data_governance: {
      data_location:         'device_only',
      server_transmission:   false,
      pii_in_export:         false,
      right_to_erasure:      true,
      consent_obtained:      !!cons.timestamp,
      raw_dates_in_export:   false,
      uses_study_day:        true
    }
  };

  const exportStr = btoa(unescape(encodeURIComponent(JSON.stringify(exportPayload, null, 2))));
  const box = el('export-box');
  box.textContent = exportStr;
  box.classList.remove('hidden');
  el('btn-copy-export').classList.remove('hidden');
  showToast(tr('export_ready'));
}

function copyExport() {
  const txt = el('export-box').textContent;
  navigator.clipboard.writeText(txt)
    .then(() => showToast(tr('copied')))
    .catch(() => showToast(tr('copy_manual')));
}


/* ── 2. PATIENT HEALTH SUMMARY (printable → PDF) ────────── */
/* This report is OWNED BY THE PATIENT.
   It contains full personal health information.
   It is completely separate from the research export. */
function generatePatientReport() {
  const prof  = DB.get('profile')     || {};
  const meds  = DB.get('medications')  || [];
  const syms  = DB.get('symptoms')     || [];
  const appts = DB.get('appointments') || [];
  const todayStats = Adherence.getTodayStats();
  const weeklyStats = Adherence.getWeeklyStats();
  const today = new Date().toISOString().split('T')[0];

  const report = el('patient-report');
  report.textContent = '';  // Clear previous content

  // Close button
  const closeBtn = document.createElement('button');
  closeBtn.className = 'report-close';
  closeBtn.textContent = tr('report_close');
  closeBtn.addEventListener('click', () => report.classList.remove('show'));
  report.appendChild(closeBtn);

  // Print button
  const printBtn = document.createElement('button');
  printBtn.className = 'report-print';
  printBtn.textContent = tr('report_print');
  printBtn.addEventListener('click', () => window.print());
  report.appendChild(printBtn);

  // Title
  const h1 = document.createElement('h1');
  h1.textContent = tr('patient_report');
  report.appendChild(h1);

  const meta = document.createElement('div');
  meta.className = 'report-meta';
  meta.textContent = tr('report_date') + ': ' + today;
  report.appendChild(meta);

  // Patient name
  const nameSection = document.createElement('div');
  nameSection.className = 'report-section';
  const nameLabel = document.createElement('p');
  nameLabel.style.cssText = 'font-size:0.75rem;color:#999;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:4px;';
  nameLabel.textContent = tr('report_name');
  const nameVal = document.createElement('p');
  nameVal.style.cssText = 'font-size:1.1rem;font-weight:700;';
  nameVal.textContent = prof.name || tr('report_no_data');
  nameSection.appendChild(nameLabel);
  nameSection.appendChild(nameVal);
  report.appendChild(nameSection);

  // Current medications
  const medsSection = document.createElement('div');
  medsSection.className = 'report-section';
  const medsH2 = document.createElement('h2');
  medsH2.textContent = tr('report_current_meds');
  medsSection.appendChild(medsH2);

  if (meds.length === 0) {
    const p = document.createElement('p');
    p.style.cssText = 'color:#999;font-size:0.85rem;';
    p.textContent = tr('report_no_data');
    medsSection.appendChild(p);
  } else {
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    thead.innerHTML = '<tr><th>' + tr('med_name') + '</th><th>' + tr('med_dose') + '</th><th>' + tr('schedule') + '</th></tr>';
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    meds.forEach(m => {
      const tr_el = document.createElement('tr');
      const parts = [];
      if (m.morning)   parts.push(tr('med_morning') + (m.morning_time ? ' '+m.morning_time : ''));
      if (m.afternoon) parts.push(tr('med_afternoon') + (m.afternoon_time ? ' '+m.afternoon_time : ''));
      if (m.night)     parts.push(tr('med_night') + (m.night_time ? ' '+m.night_time : ''));
      tr_el.innerHTML = '<td>' + escapeHtml(m.name) + '</td><td>' + escapeHtml(m.dose) + '</td><td>' + escapeHtml(parts.join(', ') || tr('as_needed')) + '</td>';
      tbody.appendChild(tr_el);
    });
    table.appendChild(tbody);
    medsSection.appendChild(table);
  }
  report.appendChild(medsSection);

  // Adherence summary
  const adhSection = document.createElement('div');
  adhSection.className = 'report-section';
  const adhH2 = document.createElement('h2');
  adhH2.textContent = tr('report_adherence');
  adhSection.appendChild(adhH2);
  const adhP = document.createElement('p');
  adhP.style.cssText = 'font-size:0.9rem;line-height:1.7;';
  adhP.innerHTML = tr('adherence_today') + ': <strong>' + todayStats.adherencePct + '%</strong> (' + todayStats.takenCount + '/' + todayStats.totalScheduled + ' ' + tr('of_doses') + ')<br>' +
    tr('weekly_adherence') + ': <strong>' + weeklyStats.adherencePct + '%</strong> (' + weeklyStats.takenCount + '/' + weeklyStats.totalScheduled + ' ' + tr('of_doses') + ')';
  adhSection.appendChild(adhP);
  report.appendChild(adhSection);

  // Recent symptoms
  const symSection = document.createElement('div');
  symSection.className = 'report-section';
  const symH2 = document.createElement('h2');
  symH2.textContent = tr('report_symptoms');
  symSection.appendChild(symH2);

  const recentSyms = syms.slice().reverse().slice(0, 5);
  if (recentSyms.length === 0) {
    const p = document.createElement('p');
    p.style.cssText = 'color:#999;font-size:0.85rem;';
    p.textContent = tr('report_no_data');
    symSection.appendChild(p);
  } else {
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    thead.innerHTML = '<tr><th>' + tr('sym_date') + '</th><th>' + tr('pain_level') + '</th><th>BP</th><th>' + tr('temperature') + '</th></tr>';
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    recentSyms.forEach(s => {
      const tr_el = document.createElement('tr');
      const bpVal = s.bp_sys ? s.bp_sys + '/' + s.bp_dia : '—';
      tr_el.innerHTML = '<td>' + escapeHtml(s.date) + '</td><td>' + (s.pain ?? '—') + '/10</td><td>' + bpVal + '</td><td>' + (s.temp ?? '—') + '°C</td>';
      tbody.appendChild(tr_el);
    });
    table.appendChild(tbody);
    symSection.appendChild(table);
  }
  report.appendChild(symSection);

  // Upcoming appointments
  const apptSection = document.createElement('div');
  apptSection.className = 'report-section';
  const apptH2 = document.createElement('h2');
  apptH2.textContent = tr('report_appointments');
  apptSection.appendChild(apptH2);

  const upcoming = appts
    .filter(a => a.date >= today)
    .sort((a,b) => (a.date + (a.time||'')).localeCompare(b.date + (b.time||'')))
    .slice(0, 5);

  if (upcoming.length === 0) {
    const p = document.createElement('p');
    p.style.cssText = 'color:#999;font-size:0.85rem;';
    p.textContent = tr('no_upcoming_appts');
    apptSection.appendChild(p);
  } else {
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    thead.innerHTML = '<tr><th>' + tr('appt_date') + '</th><th>' + tr('appt_time') + '</th><th>' + tr('appt_doctor') + '</th></tr>';
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    upcoming.forEach(a => {
      const tr_el = document.createElement('tr');
      tr_el.innerHTML = '<td>' + escapeHtml(a.date) + '</td><td>' + escapeHtml(a.time||'') + '</td><td>' + escapeHtml(a.doctor) + '</td>';
      tbody.appendChild(tr_el);
    });
    table.appendChild(tbody);
    apptSection.appendChild(table);
  }
  report.appendChild(apptSection);

  // Emergency contact
  const emergSection = document.createElement('div');
  emergSection.className = 'report-section';
  const emergH2 = document.createElement('h2');
  emergH2.textContent = tr('report_emergency');
  emergSection.appendChild(emergH2);
  const emergP = document.createElement('p');
  emergP.style.cssText = 'font-size:0.9rem;line-height:1.7;';
  emergP.innerHTML = escapeHtml(prof.emerg_name || '—') + '<br>' + escapeHtml(prof.emerg_rel || '') + '<br>' + escapeHtml(prof.emerg_phone || '—');
  emergSection.appendChild(emergP);
  report.appendChild(emergSection);

  // Show the report
  report.classList.add('show');
}

/* Helper: escape HTML for report tables (uses textContent internally via DOM) */
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}
