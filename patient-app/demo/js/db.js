/* ═══════════════════════════════════════════════════════════════
   PMAS — Database Layer (localStorage wrapper)
   Offline-first: data lives on the device by default. The optional
   Account & Cloud Sync (api.js) sends selected records only to the
   PMAS server the user connects to. Not encrypted storage.
   ═══════════════════════════════════════════════════════════════ */

/* ── Safe localStorage wrapper ───────────────────────────── */
const DB = {
  PREFIX: 'pmas_',
  VERSION: '1.1.0',

  get(k) {
    try {
      return JSON.parse(localStorage.getItem(this.PREFIX + k));
    } catch(e) {
      console.warn('DB read error for key:', k, e);
      return null;
    }
  },

  set(k, v) {
    try {
      localStorage.setItem(this.PREFIX + k, JSON.stringify(v));
    } catch(e) {
      showToast('Storage error');
    }
  },

  del(k) {
    localStorage.removeItem(this.PREFIX + k);
  },

  clearAll() {
    const keys = [
      'profile', 'medications', 'symptoms', 'appointments',
      'consent', 'adherence', 'study_meta', 'reminder_state'
    ];
    keys.forEach(k => localStorage.removeItem(this.PREFIX + k));
  }
};

/* ── Study ID Assignment ──────────────────────────────────── */
/* Patient identity is maintained separately from the research dataset.
   Study ID is assigned on first consent and persists. */
const StudyID = {
  get() {
    let meta = DB.get('study_meta');
    if (!meta) {
      // Assign next sequential ID
      const nextNum = this.getNextNumber();
      meta = {
        study_id: 'PMAS-' + String(nextNum).padStart(3, '0'),
        assigned_ts: new Date().toISOString(),
        baseline_date: null  // Set when first consent is accepted
      };
      DB.set('study_meta', meta);
    }
    return meta;
  },

  getNextNumber() {
    // Since we're local-only, we use a stored counter
    // In a real study, IDs would be pre-assigned by the research team
    let meta = DB.get('study_meta');
    if (meta && meta.study_id) {
      const match = meta.study_id.match(/PMAS-(\d+)/);
      if (match) return parseInt(match[1]) + 1;
    }
    return 1;
  },

  setBaseline(dateStr) {
    const meta = this.get();
    meta.baseline_date = dateStr || new Date().toISOString().split('T')[0];
    DB.set('study_meta', meta);
  },

  getStudyDay() {
    /* Study Day 0 = baseline date.
       Study Day 1 = day after baseline, etc.
       This replaces raw dates in the research export. */
    const meta = this.get();
    if (!meta.baseline_date) return 0;
    const baseline = new Date(meta.baseline_date + 'T00:00:00');
    const today = new Date(new Date().toISOString().split('T')[0] + 'T00:00:00');
    const diffMs = today - baseline;
    return Math.floor(diffMs / 86400000);
  },

  dateToStudyDay(dateStr) {
    const meta = this.get();
    if (!meta.baseline_date) return 0;
    const baseline = new Date(meta.baseline_date + 'T00:00:00');
    const target = new Date(dateStr + 'T00:00:00');
    const diffMs = target - baseline;
    return Math.floor(diffMs / 86400000);
  }
};

/* ── Adherence Data Layer ─────────────────────────────────── */
/* Adherence records are stored separately from medications.
   Each record: { id, med_id, date, slot, status, recorded_ts }
   slot: 'morning' | 'afternoon' | 'night'
   status: 'taken' | 'delayed' | 'missed' */
const Adherence = {
  getAll() {
    return DB.get('adherence') || [];
  },

  getByDate(dateStr) {
    return this.getAll().filter(a => a.date === dateStr);
  },

  getByDateRange(startDate, endDate) {
    return this.getAll().filter(a => a.date >= startDate && a.date <= endDate);
  },

  record(medId, date, slot, status) {
    const records = this.getAll();
    // Find existing record for this med+date+slot
    const idx = records.findIndex(
      r => r.med_id === medId && r.date === date && r.slot === slot
    );
    const entry = {
      med_id: medId,
      date: date,
      slot: slot,
      status: status,
      recorded_ts: new Date().toISOString()
    };
    if (idx >= 0) {
      records[idx] = entry;
    } else {
      records.push(entry);
    }
    DB.set('adherence', records);
  },

  getStatus(medId, date, slot) {
    const records = this.getAll();
    const found = records.find(
      r => r.med_id === medId && r.date === date && r.slot === slot
    );
    return found ? found.status : null;
  },

  /* Calculate today's adherence percentage */
  getTodayStats() {
    const today = new Date().toISOString().split('T')[0];
    const meds = DB.get('medications') || [];
    const activeMeds = meds.filter(m => {
      return (!m.start_date || m.start_date <= today) &&
             (!m.end_date || m.end_date >= today);
    });

    let totalScheduled = 0;
    let totalRecorded = 0;
    let takenCount = 0;

    activeMeds.forEach(m => {
      if (m.morning) { totalScheduled++; if (this.getStatus(m.id, today, 'morning')) totalRecorded++; if (this.getStatus(m.id, today, 'morning') === 'taken') takenCount++; }
      if (m.afternoon) { totalScheduled++; if (this.getStatus(m.id, today, 'afternoon')) totalRecorded++; if (this.getStatus(m.id, today, 'afternoon') === 'taken') takenCount++; }
      if (m.night) { totalScheduled++; if (this.getStatus(m.id, today, 'night')) totalRecorded++; if (this.getStatus(m.id, today, 'night') === 'taken') takenCount++; }
    });

    return {
      totalScheduled,
      totalRecorded,
      takenCount,
      adherencePct: totalScheduled > 0 ? Math.round((takenCount / totalScheduled) * 100) : 0
    };
  },

  /* Calculate weekly adherence (last 7 days) */
  getWeeklyStats() {
    const today = new Date();
    let totalScheduled = 0;
    let takenCount = 0;
    let daysWithRecords = 0;
    const meds = DB.get('medications') || [];

    for (let i = 0; i < 7; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const dateStr = d.toISOString().split('T')[0];
      const activeMeds = meds.filter(m => {
        return (!m.start_date || m.start_date <= dateStr) &&
               (!m.end_date || m.end_date >= dateStr);
      });

      let dayScheduled = 0;
      let dayTaken = 0;

      activeMeds.forEach(m => {
        if (m.morning) { dayScheduled++; if (this.getStatus(m.id, dateStr, 'morning') === 'taken') dayTaken++; }
        if (m.afternoon) { dayScheduled++; if (this.getStatus(m.id, dateStr, 'afternoon') === 'taken') dayTaken++; }
        if (m.night) { dayScheduled++; if (this.getStatus(m.id, dateStr, 'night') === 'taken') dayTaken++; }
      });

      totalScheduled += dayScheduled;
      takenCount += dayTaken;
      if (dayScheduled > 0) daysWithRecords++;
    }

    return {
      totalScheduled,
      takenCount,
      daysWithRecords,
      adherencePct: totalScheduled > 0 ? Math.round((takenCount / totalScheduled) * 100) : 0
    };
  }
};
