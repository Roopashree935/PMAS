/* ═══════════════════════════════════════════════════════════════
   PMAS — Adherence Module
   Taken / Delayed / Missed tracking for each scheduled dose.
   This is the core feature that connects the intervention
   to the research question on medication adherence.
   ═══════════════════════════════════════════════════════════════ */

/* ── Record a dose status ────────────────────────────────── */
function recordDose(medId, slot, status) {
  const today = clinicalDateKey();
  Adherence.record(medId, today, slot, status);
  // Cloud sync: push the dose (and any other pending records) when signed in
  if (typeof API !== 'undefined' && API.isAuthenticated()) {
    API.syncPending().catch(() => {});
  }
  showToast(tr('dose_recorded'));
  renderMedications();
  updateDashboard();
}

/* ── Build adherence section for a medication card ───────── */
function createAdherenceSection(med) {
  const today = clinicalDateKey();
  const section = document.createElement('div');
  section.className = 'adherence-section';

  const label = document.createElement('div');
  label.className = 'adherence-label';
  label.textContent = tr('today_doses');
  section.appendChild(label);

  const slots = [
    { key: 'morning', label: tr('med_morning'), enabled: med.morning, time: med.morning_time },
    { key: 'afternoon', label: tr('med_afternoon'), enabled: med.afternoon, time: med.afternoon_time },
    { key: 'night', label: tr('med_night'), enabled: med.night, time: med.night_time }
  ];

  const activeSlots = slots.filter(s => s.enabled);
  if (activeSlots.length === 0) {
    const none = document.createElement('p');
    none.className = 'text-muted';
    none.style.fontSize = '0.78rem';
    none.textContent = tr('no_doses_today');
    section.appendChild(none);
    return section;
  }

  activeSlots.forEach(slot => {
    const row = document.createElement('div');
    row.className = 'dose-row';

    // Time/label
    const timeEl = document.createElement('span');
    timeEl.className = 'dose-time';
    timeEl.textContent = slot.label + (slot.time ? ' ' + slot.time : '');
    row.appendChild(timeEl);

    // Current status badge
    const currentStatus = Adherence.getStatus(med.id, today, slot.key);
    if (currentStatus) {
      const badge = document.createElement('span');
      badge.className = 'dose-status ' + currentStatus;
      badge.textContent = currentStatus === 'taken' ? tr('dose_taken') :
                          currentStatus === 'delayed' ? tr('dose_delayed') :
                          tr('dose_missed');
      row.appendChild(badge);
    }

    // Action buttons
    const actions = document.createElement('div');
    actions.className = 'dose-actions';

    const slots_config = [
      { status: 'taken', label: tr('take_dose'), cls: 'taken-btn' },
      { status: 'delayed', label: tr('delayed_dose'), cls: 'delayed-btn' },
      { status: 'missed', label: tr('missed_dose'), cls: 'missed-btn' }
    ];

    slots_config.forEach(sc => {
      const btn = document.createElement('button');
      btn.className = 'dose-btn ' + sc.cls;
      if (currentStatus === sc.status) btn.classList.add('active');
      btn.textContent = sc.label;
      btn.addEventListener('click', () => recordDose(med.id, slot.key, sc.status));
      actions.appendChild(btn);
    });

    row.appendChild(actions);
    section.appendChild(row);
  });

  return section;
}

/* ── Build adherence bar for dashboard ───────────────────── */
function createAdherenceBar(pct, label, sublabel) {
  const wrap = document.createElement('div');
  wrap.style.marginBottom = '0.75rem';

  const lbl = document.createElement('div');
  lbl.className = 'adherence-label';
  lbl.textContent = label;
  wrap.appendChild(lbl);

  const barWrap = document.createElement('div');
  barWrap.className = 'adherence-bar-wrap';
  const barFill = document.createElement('div');
  barFill.className = 'adherence-bar-fill';
  let barClass = 'good';
  if (pct < 50) barClass = 'poor';
  else if (pct < 80) barClass = 'ok';
  barFill.classList.add(barClass);
  barFill.style.width = pct + '%';
  barWrap.appendChild(barFill);
  wrap.appendChild(barWrap);

  const txt = document.createElement('div');
  txt.className = 'adherence-text';
  const leftSpan = document.createElement('span');
  leftSpan.textContent = pct + '%';
  const rightSpan = document.createElement('span');
  rightSpan.textContent = sublabel;
  txt.appendChild(leftSpan);
  txt.appendChild(rightSpan);
  wrap.appendChild(txt);

  return wrap;
}
