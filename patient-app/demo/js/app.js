/* ═══════════════════════════════════════════════════════════════
   PMAS — Core Application Logic
   ───────────────────────────────────────────────────────────────
   Changes from v1.0:
   ✅ Granular consent (6 separate acknowledgements)
   ✅ Adherence tracking (Taken/Delayed/Missed)
   ✅ Study ID + de-identified export
   ✅ Safety escalation (not diagnosis)
   ✅ Complete multilingual patient-facing text
   ✅ Local reminders
   ✅ Patient PDF report (separate from research export)
   ✅ Fixed "Next Medication Due" logic
   ✅ Fixed appointment date+time sorting
   ✅ Removed user-scalable=no
   ═══════════════════════════════════════════════════════════════ */
"use strict";

/* ── Safe DOM helpers ────────────────────────────────────── */
function el(id) { return document.getElementById(id); }

function setText(id, str) {
  const node = el(id);
  if (node) node.textContent = str ?? '';
}

function safeAttr(id, attr, val) {
  const node = el(id);
  if (node) node[attr] = val ?? '';
}

/* ── Toast notification ──────────────────────────────────── */
function showToast(msg, duration) {
  const t = el('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration || 2400);
}

/* ── Language ────────────────────────────────────────────── */
let lang = 'en';

function changeLang(code) {
  lang = T[code] ? code : 'en';
  applyTranslations();
  // Save preference
  const consent = DB.get('consent');
  if (consent) { consent.language = lang; DB.set('consent', consent); }
}

/* Apply all translations to the DOM */
function applyTranslations() {
  const selectors = [
    ['data-i18n', 'textContent'],
    ['data-i18n-ph', 'placeholder'],
    ['data-i18n-aria', 'aria-label']
  ];

  selectors.forEach(([attr, prop]) => {
    document.querySelectorAll('[' + attr + ']').forEach(node => {
      const key = node.getAttribute(attr);
      if (key) {
        node[prop] = tr(key);
      }
    });
  });

  // Update select options
  document.querySelectorAll('[data-i18n-opt]').forEach(opt => {
    const key = opt.getAttribute('data-i18n-opt');
    if (key) opt.textContent = tr(key);
  });

  // Update dynamic content
  updateDashboard();
  renderMedications();
  renderSymptoms();
  renderAppts();
}

/* ── Granular Consent ────────────────────────────────────── */
function acceptConsent() {
  // Check all 6 consent boxes
  const checks = ['consent-check1','consent-check2','consent-check3',
                  'consent-check4','consent-check5','consent-check6'];
  for (const id of checks) {
    if (!el(id).checked) {
      showToast(tr('consent_all_required'));
      return;
    }
  }

  // Assign Study ID and set baseline
  const studyMeta = StudyID.get();
  StudyID.setBaseline();

  DB.set('consent', {
    timestamp: new Date().toISOString(),
    version: DB.VERSION,
    language: lang,
    checks: checks.map(id => el(id).checked)
  });

  el('consent-screen').classList.add('hidden');
  el('app-core').classList.remove('hidden');
  setTodayDates();
  applyTranslations();
  renderAll();
  Reminders.start();
}

/* ── Tab switching ───────────────────────────────────────── */
function switchTab(tabId, btn) {
  document.querySelectorAll('.tab').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  el('tab-' + tabId).classList.add('active');
  if (btn) btn.classList.add('active');
  if (tabId === 'dashboard') updateDashboard();
}

/* ── Set today as default date ───────────────────────────── */
function setTodayDates() {
  const today = new Date().toISOString().split('T')[0];
  ['sym-date','appt-date','med-start'].forEach(id => {
    if (el(id) && !el(id).value) el(id).value = today;
  });
}

/* ── Toggle time input with checkbox ────────────────────── */
function toggleTime(timeId, enabled) {
  const inp = el(timeId);
  inp.disabled = !enabled;
  if (!enabled) inp.value = '';
}

/* ── Dashboard update (fixed Next Medication Due logic) ─── */
function updateDashboard() {
  const prof  = DB.get('profile')     || {};
  const meds  = DB.get('medications')  || [];
  const syms  = DB.get('symptoms')     || [];
  const appts = DB.get('appointments') || [];
  const todayStats = Adherence.getTodayStats();
  const weeklyStats = Adherence.getWeeklyStats();

  setText('dash-name', prof.name || 'Patient');
  setText('stat-meds', meds.filter(m => {
    const today = new Date().toISOString().split('T')[0];
    return (!m.start_date || m.start_date <= today) && (!m.end_date || m.end_date >= today);
  }).length);
  setText('stat-syms', syms.length);

  // Today's adherence
  if (el('stat-adherence')) {
    setText('stat-adherence', todayStats.adherencePct + '%');
  }

  // ═══ FIXED: Next Medication Due logic ═══
  // Instead of showing activeMeds[0], calculate the actual next
  // scheduled dose based on current time.
  const today = new Date().toISOString().split('T')[0];
  const now = new Date();
  const currentMinutes = now.getHours() * 60 + now.getMinutes();

  const activeMeds = meds.filter(m => {
    return (!m.start_date || m.start_date <= today) &&
           (!m.end_date || m.end_date >= today);
  });

  let nextMedText = '—';
  let nextMedFound = false;

  if (activeMeds.length > 0) {
    // Collect all upcoming doses for today
    const upcomingDoses = [];
    activeMeds.forEach(m => {
      const slots = [
        { time: m.morning_time,   enabled: m.morning,   label: tr('med_morning') },
        { time: m.afternoon_time, enabled: m.afternoon, label: tr('med_afternoon') },
        { time: m.night_time,     enabled: m.night,     label: tr('med_night') }
      ];
      slots.forEach(s => {
        if (s.enabled && s.time) {
          const [h, min] = s.time.split(':').map(Number);
          const doseMinutes = h * 60 + min;
          if (doseMinutes >= currentMinutes) {
            upcomingDoses.push({ med: m, time: s.time, minutes: doseMinutes, label: s.label });
          }
        }
      });
    });

    // Sort by time ascending
    upcomingDoses.sort((a, b) => a.minutes - b.minutes);

    if (upcomingDoses.length > 0) {
      const next = upcomingDoses[0];
      nextMedText = next.med.name + ' · ' + next.med.dose + ' · ' + next.time;
      nextMedFound = true;
    } else {
      // No more doses today — check if there's any active med at all
      nextMedText = tr('no_active_meds');
    }
  } else {
    nextMedText = meds.length > 0 ? tr('no_active_meds') : tr('none_added');
  }

  setText('dash-next-med', nextMedText);

  // Today's adherence bar
  const adhWrap = el('dash-adherence-wrap');
  if (adhWrap) {
    adhWrap.textContent = '';
    if (todayStats.totalScheduled > 0) {
      const bar = createAdherenceBar(
        todayStats.adherencePct,
        tr('adherence_today'),
        todayStats.takenCount + '/' + todayStats.totalScheduled + ' ' + tr('doses_taken')
      );
      adhWrap.appendChild(bar);
    }
  }

  // Weekly adherence bar
  const weeklyWrap = el('dash-weekly-wrap');
  if (weeklyWrap) {
    weeklyWrap.textContent = '';
    if (weeklyStats.totalScheduled > 0) {
      const bar = createAdherenceBar(
        weeklyStats.adherencePct,
        tr('weekly_adherence'),
        weeklyStats.takenCount + '/' + weeklyStats.totalScheduled + ' ' + tr('doses_taken')
      );
      weeklyWrap.appendChild(bar);
    }
  }

  // Latest symptom
  if (syms.length > 0) {
    const last = syms[syms.length - 1];
    setText('dash-last-sym', last.date + ' · ' + tr('pain_level').split('(')[0].trim() + ': ' + (last.pain ?? '—') + '/10');
  } else {
    setText('dash-last-sym', tr('no_entries'));
  }

  // ═══ FIXED: Next appointment (date + time sorting) ═══
  const upcoming = appts
    .filter(a => a.date >= today)
    .sort((a, b) => {
      const aKey = a.date + (a.time || '00:00');
      const bKey = b.date + (b.time || '00:00');
      return aKey.localeCompare(bKey);
    });
  if (upcoming.length > 0) {
    const a = upcoming[0];
    setText('dash-next-appt', a.date + ' · ' + (a.time || '') + ' · ' + a.doctor);
  } else {
    setText('dash-next-appt', tr('no_upcoming_appts'));
  }

  // Emergency contact
  setText('dash-emerg-name', prof.emerg_name || tr('not_set'));
  setText('dash-emerg-rel', prof.emerg_rel || '');
  const phone = prof.emerg_phone || '';
  setText('dash-emerg-phone', phone || '—');
  safeAttr('dash-emerg-phone', 'href', 'tel:' + phone);
  safeAttr('modal-call-btn', 'href', 'tel:' + phone);
}

/* ── Profile ────────────────────────────────────────────── */
function loadProfileForm() {
  const p = DB.get('profile') || {};
  const set = (id, val) => { if (el(id)) el(id).value = val || ''; };
  set('prof-name', p.name);
  set('prof-dob', p.dob);
  set('prof-gender', p.gender);
  set('prof-blood', p.blood);
  set('prof-allergy', p.allergy);
  set('prof-chronic', p.chronic);
  set('prof-emerg-name', p.emerg_name);
  set('prof-emerg-rel', p.emerg_rel);
  set('prof-emerg-phone', p.emerg_phone);
}

function saveProfile(e) {
  e.preventDefault();
  const nameVal = el('prof-name').value.trim();
  const emerName = el('prof-emerg-name').value.trim();
  const emerPhone = el('prof-emerg-phone').value.trim();

  if (!nameVal || !emerName || !emerPhone) {
    showToast(tr('val_required'));
    return;
  }

  // Validate Indian phone number
  const phoneClean = emerPhone.replace(/[\s\-]/g, '');
  const phoneValid = /^(?:\+91\d{10}|\d{10})$/.test(phoneClean);
  if (!phoneValid) {
    showToast(tr('val_phone'));
    return;
  }

  DB.set('profile', {
    name:        nameVal,
    dob:         el('prof-dob').value,
    gender:      el('prof-gender').value,
    blood:       el('prof-blood').value,
    allergy:     el('prof-allergy').value.trim(),
    chronic:     el('prof-chronic').value.trim(),
    emerg_name:  emerName,
    emerg_rel:   el('prof-emerg-rel').value.trim(),
    emerg_phone: phoneClean
  });
  updateDashboard();
  showToast(tr('profile_saved'));
}

/* ── Medications CRUD ────────────────────────────────────── */
function toggleMedForm() {
  el('med-form-wrap').classList.toggle('hidden');
}

function saveMedication(e) {
  e.preventDefault();
  const name = el('med-name').value.trim();
  const dose = el('med-dose').value.trim();
  const start = el('med-start').value;
  const end = el('med-end').value;

  if (!name || !dose || !start || !end) {
    showToast(tr('val_required'));
    return;
  }
  if (end < start) {
    showToast(tr('val_end_after_start'));
    return;
  }

  const meds = DB.get('medications') || [];
  meds.push({
    id:             'med_' + Date.now(),
    name:           name,
    dose:           dose,
    morning:        el('med-morn').checked,
    morning_time:   el('med-morn-time').value,
    afternoon:      el('med-aft').checked,
    afternoon_time: el('med-aft-time').value,
    night:          el('med-ngt').checked,
    night_time:     el('med-ngt-time').value,
    start_date:     start,
    end_date:       end,
    notes:          el('med-notes').value.trim()
  });
  DB.set('medications', meds);
  el('med-form').reset();
  ['med-morn-time','med-aft-time','med-ngt-time'].forEach(id => { el(id).disabled = true; });
  el('med-form-wrap').classList.add('hidden');
  renderMedications();
  updateDashboard();
  showToast(tr('med_saved'));
}

function deleteMed(id) {
  if (!confirm(tr('remove_med'))) return;
  DB.set('medications', (DB.get('medications')||[]).filter(m => m.id !== id));
  renderMedications();
  updateDashboard();
  showToast(tr('med_removed'));
}

/* ── Safe element creators (no innerHTML with user data) ─── */
function createMedCard(med) {
  const wrap = document.createElement('div');
  wrap.className = 'med-item';

  // Header row
  const head = document.createElement('div');
  head.className = 'med-item-head';

  const body = document.createElement('div');

  const title = document.createElement('h3');
  title.textContent = med.name;
  const dose = document.createElement('span');
  dose.className = 'med-dose';
  dose.textContent = med.dose;
  title.appendChild(dose);

  const sched = document.createElement('p');
  sched.className = 'med-sched';
  const parts = [];
  if (med.morning)   parts.push(tr('med_morning')   + (med.morning_time   ? ' ' + med.morning_time   : ''));
  if (med.afternoon) parts.push(tr('med_afternoon') + (med.afternoon_time ? ' ' + med.afternoon_time : ''));
  if (med.night)     parts.push(tr('med_night')     + (med.night_time     ? ' ' + med.night_time     : ''));
  sched.textContent = tr('schedule') + ': ' + (parts.join(' · ') || tr('as_needed'));

  const dates = document.createElement('p');
  dates.className = 'med-sched';
  dates.textContent = (med.start_date || '') + ' → ' + (med.end_date || '');

  body.appendChild(title);
  body.appendChild(sched);
  if (med.start_date) body.appendChild(dates);

  const delBtn = document.createElement('button');
  delBtn.className = 'del-btn';
  delBtn.textContent = '×';
  delBtn.setAttribute('aria-label', tr('remove_med'));
  delBtn.addEventListener('click', () => deleteMed(med.id));

  head.appendChild(body);
  head.appendChild(delBtn);
  wrap.appendChild(head);

  // Adherence section (NEW)
  wrap.appendChild(createAdherenceSection(med));

  return wrap;
}

function renderMedications() {
  const container = el('med-list');
  if (!container) return;
  container.textContent = '';
  const meds = DB.get('medications') || [];
  if (meds.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    const icon = document.createElement('span');
    icon.textContent = '💊';
    empty.appendChild(icon);
    empty.appendChild(document.createTextNode(tr('no_meds_added')));
    container.appendChild(empty);
    return;
  }
  meds.forEach(m => container.appendChild(createMedCard(m)));
}

/* ── Symptoms CRUD (redesigned safety logic) ────────────── */
function saveSymptom(e) {
  e.preventDefault();
  const dateVal = el('sym-date').value;
  if (!dateVal) { showToast(tr('val_date_required')); return; }

  const pain = parseInt(el('sym-pain').value);
  const sys  = parseInt(el('sym-bp-sys').value) || 0;
  const dia  = parseInt(el('sym-bp-dia').value) || 0;
  const temp = parseFloat(el('sym-temp').value) || null;
  const wt   = parseFloat(el('sym-weight').value) || null;

  if (temp && (temp < 35 || temp > 42)) { showToast(tr('val_temp_range')); return; }
  if (sys && (sys < 60 || sys > 250))   { showToast(tr('val_bp_sys_range')); return; }
  if (dia && (dia < 40 || dia > 150))   { showToast(tr('val_bp_dia_range')); return; }

  const syms = DB.get('symptoms') || [];
  syms.push({
    id:           'sym_' + Date.now(),
    date:         dateVal,
    pain:         pain,
    temp:         temp,
    weight:       wt,
    bp_sys:       sys || null,
    bp_dia:       dia || null,
    symptoms:     el('sym-symptoms').value.trim(),
    side_effects: el('sym-side').value.trim(),
    notes:        el('sym-notes').value.trim()
  });
  DB.set('symptoms', syms);

  // ═══ REDESIGNED: Safety escalation, NOT diagnosis ═══
  // A single high reading doesn't automatically mean "emergency."
  // Instead, escalate with a safety advisory that recommends
  // professional evaluation without diagnosing.
  if (pain >= 8 || sys >= 180) {
    showSafetyAlert();
  } else {
    showToast(tr('sym_logged'));
  }

  el('sym-form').reset();
  el('pain-val').textContent = '0';
  setTodayDates();
  renderSymptoms();
  updateDashboard();
}

function deleteSym(id) {
  if (!confirm(tr('delete_entry'))) return;
  DB.set('symptoms', (DB.get('symptoms')||[]).filter(s => s.id !== id));
  renderSymptoms();
  updateDashboard();
  showToast(tr('sym_deleted'));
}

function createSymCard(s) {
  const wrap = document.createElement('div');
  wrap.className = 'sym-item';

  const dateEl = document.createElement('div');
  dateEl.className = 'sym-date';
  dateEl.textContent = s.date;
  wrap.appendChild(dateEl);

  const chips = document.createElement('div');
  chips.className = 'sym-chips';

  const addChip = (label, val, unit = '') => {
    if (val === undefined || val === null || val === '') return;
    const c = document.createElement('span');
    c.className = 'chip';
    c.textContent = label + ': ' + val + unit;
    chips.appendChild(c);
  };

  addChip(tr('pain_level').split('(')[0].trim(), s.pain, '/10');
  addChip(tr('temperature').split('(')[0].trim(), s.temp, '°C');
  addChip(tr('weight').split('(')[0].trim(), s.weight, 'kg');
  if (s.bp_sys) addChip('BP', s.bp_sys + '/' + (s.bp_dia || '?'), ' mmHg');
  wrap.appendChild(chips);

  if (s.symptoms) {
    const p = document.createElement('p');
    p.className = 'text-muted';
    p.style.marginTop = '5px';
    p.textContent = s.symptoms;
    wrap.appendChild(p);
  }

  const delBtn = document.createElement('button');
  delBtn.className = 'del-btn';
  delBtn.textContent = '×';
  delBtn.setAttribute('aria-label', tr('delete_entry'));
  delBtn.style.float = 'right';
  delBtn.addEventListener('click', () => deleteSym(s.id));
  wrap.insertBefore(delBtn, wrap.firstChild);

  return wrap;
}

function renderSymptoms() {
  const container = el('sym-list');
  if (!container) return;
  container.textContent = '';
  const syms = (DB.get('symptoms') || []).slice().reverse();
  if (syms.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    const icon = document.createElement('span');
    icon.textContent = '📋';
    empty.appendChild(icon);
    empty.appendChild(document.createTextNode(tr('no_sym_entries')));
    container.appendChild(empty);
    return;
  }
  syms.forEach(s => container.appendChild(createSymCard(s)));
}

/* ── Appointments CRUD (fixed date+time sorting) ────────── */
function toggleApptForm() {
  el('appt-form-wrap').classList.toggle('hidden');
}

function saveAppt(e) {
  e.preventDefault();
  const date   = el('appt-date').value;
  const time   = el('appt-time').value;
  const doctor = el('appt-doctor').value.trim();
  if (!date || !time || !doctor) { showToast(tr('val_required')); return; }

  const appts = DB.get('appointments') || [];
  appts.push({
    id:     'appt_' + Date.now(),
    date:   date,
    time:   time,
    doctor: doctor,
    dept:   el('appt-dept').value.trim(),
    notes:  el('appt-notes').value.trim()
  });
  DB.set('appointments', appts);
  el('appt-form').reset();
  el('appt-form-wrap').classList.add('hidden');
  renderAppts();
  updateDashboard();
  showToast(tr('appt_saved'));
}

function deleteAppt(id) {
  if (!confirm(tr('delete_appt'))) return;
  DB.set('appointments', (DB.get('appointments')||[]).filter(a => a.id !== id));
  renderAppts();
  updateDashboard();
  showToast(tr('appt_deleted'));
}

function createApptCard(a) {
  const wrap = document.createElement('div');
  wrap.className = 'appt-item';

  const d = a.date ? new Date(a.date + 'T00:00:00') : null;

  const dateBlock = document.createElement('div');
  dateBlock.className = 'appt-date-block';
  const dayEl = document.createElement('div');
  dayEl.className = 'appt-day';
  dayEl.textContent = d ? d.getDate() : '—';
  const monEl = document.createElement('div');
  monEl.className = 'appt-mon';
  monEl.textContent = d ? d.toLocaleString('default', {month: 'short'}) : '';
  dateBlock.appendChild(dayEl);
  dateBlock.appendChild(monEl);

  const body = document.createElement('div');
  body.className = 'appt-body';
  const h = document.createElement('h3');
  h.textContent = a.doctor;
  const p = document.createElement('p');
  p.textContent = (a.time || '') + (a.dept ? ' · ' + a.dept : '');
  if (a.notes) {
    const n = document.createElement('p');
    n.textContent = a.notes;
    n.style.marginTop = '2px';
    body.appendChild(h);
    body.appendChild(p);
    body.appendChild(n);
  } else {
    body.appendChild(h);
    body.appendChild(p);
  }

  const delBtn = document.createElement('button');
  delBtn.className = 'del-btn';
  delBtn.textContent = '×';
  delBtn.setAttribute('aria-label', tr('delete_appt'));
  delBtn.addEventListener('click', () => deleteAppt(a.id));

  wrap.appendChild(dateBlock);
  wrap.appendChild(body);
  wrap.appendChild(delBtn);
  return wrap;
}

function renderAppts() {
  const container = el('appt-list');
  if (!container) return;
  container.textContent = '';
  // ═══ FIXED: Sort by date + time, not just date ═══
  const appts = (DB.get('appointments') || []).slice().sort((a, b) => {
    const aKey = b.date + (b.time || '00:00');
    const bKey = a.date + (a.time || '00:00');
    return aKey.localeCompare(bKey);
  });
  if (appts.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    const icon = document.createElement('span');
    icon.textContent = '📅';
    empty.appendChild(icon);
    empty.appendChild(document.createTextNode(tr('no_appts')));
    container.appendChild(empty);
    return;
  }
  appts.forEach(a => container.appendChild(createApptCard(a)));
}

function renderAll() {
  renderMedications();
  renderSymptoms();
  renderAppts();
  loadProfileForm();
}

/* ── Safety Alert Modal (redesigned — escalation, not diagnosis) ─ */
let safetyTimer = null;

function showSafetyAlert() {
  const modal = el('safety-modal');
  modal.classList.add('show');
  el('safety-dismiss-btn').style.display = 'none';
  el('safety-countdown').textContent = '';

  let secs = 5;
  el('safety-countdown').textContent = tr('dismiss_countdown') + ' ' + secs + tr('dismiss_seconds');

  safetyTimer = setInterval(() => {
    secs--;
    if (secs <= 0) {
      clearInterval(safetyTimer);
      el('safety-countdown').textContent = '';
      el('safety-dismiss-btn').style.display = 'inline-block';
    } else {
      el('safety-countdown').textContent = tr('dismiss_countdown') + ' ' + secs + tr('dismiss_seconds');
    }
  }, 1000);
}

function dismissSafetyAlert() {
  el('safety-modal').classList.remove('show');
  clearInterval(safetyTimer);
  showToast(tr('safety_logged'));
  // Reset the symptom form after safety dismissal
  el('sym-form').reset();
  el('pain-val').textContent = '0';
  setTodayDates();
  renderSymptoms();
  updateDashboard();
}

/* ── DPDP Right to Erasure ──────────────────────────────── */
function deleteAllData() {
  if (!confirm(tr('erase_confirm'))) return;
  DB.clearAll();
  window.location.reload();
}

/* ── Account & Cloud Sync (api.js bridge) ───────────────── */
function updateSyncStatus() {
  const statusEl = el('sync-status');
  const logoutBtn = el('btn-sync-logout');
  if (!statusEl) return;
  if (API.isAuthenticated()) {
    statusEl.removeAttribute('data-i18n');
    statusEl.textContent = tr('sync_signed_in');
    if (logoutBtn) logoutBtn.classList.remove('hidden');
  } else {
    statusEl.setAttribute('data-i18n', 'sync_offline');
    statusEl.textContent = tr('sync_offline');
    if (logoutBtn) logoutBtn.classList.add('hidden');
  }
}

async function syncLogin() {
  const baseUrl = (el('sync-url').value || '').trim().replace(/\/+$/, '');
  const phone = el('sync-phone').value.trim();
  const password = el('sync-pass').value;
  if (!baseUrl || !phone || !password) {
    showToast(tr('sync_fill_fields'));
    return;
  }
  try {
    localStorage.setItem('pmas_api_url', baseUrl);
    API.init(baseUrl);
    await API.login(phone, password);
    el('sync-pass').value = '';
    await API.syncPending();
    updateSyncStatus();
    showToast(tr('sync_signed_in'));
  } catch (e) {
    showToast(tr('sync_error') + ' ' + (e.message || ''));
  }
}

async function syncRegister() {
  const baseUrl = (el('sync-url').value || '').trim().replace(/\/+$/, '');
  const phone = el('sync-phone').value.trim();
  const password = el('sync-pass').value;
  if (!baseUrl || !phone || !password) {
    showToast(tr('sync_fill_fields'));
    return;
  }
  const ageBox = el('sync-age');
  if (!ageBox || !ageBox.checked) {
    showToast(tr('sync_age_error'));
    return;
  }
  try {
    localStorage.setItem('pmas_api_url', baseUrl);
    API.init(baseUrl);
    const consent = DB.get('consent');
    await API.register(phone, password, (consent && consent.language) || 'en');
    el('sync-pass').value = '';
    await API.syncPending();
    updateSyncStatus();
    showToast(tr('sync_signed_in'));
  } catch (e) {
    showToast(tr('sync_error') + ' ' + (e.message || ''));
  }
}

function syncLogout() {
  API.logout();
  updateSyncStatus();
  showToast(tr('sync_offline'));
}

/* ── Initialise ──────────────────────────────────────────── */
window.addEventListener('load', () => {
  // Cloud sync layer — safe even with no backend configured:
  // without a base URL every call silently falls back to offline mode.
  if (typeof API !== 'undefined') {
    API.init();
    updateSyncStatus();
  }

  const consent = DB.get('consent');
  if (consent) {
    lang = consent.language || 'en';
    const langSelector = el('lang-selector');
    if (langSelector) langSelector.value = lang;
    el('consent-screen').classList.add('hidden');
    el('app-core').classList.remove('hidden');
    applyTranslations();
    setTodayDates();
    renderAll();
    Reminders.start();
  } else {
    // Apply translations to consent screen
    applyTranslations();
  }

  // Set min date for appointments to today
  const today = new Date().toISOString().split('T')[0];
  if (el('appt-date')) el('appt-date').min = today;
});
