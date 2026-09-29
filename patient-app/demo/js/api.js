/* ═══════════════════════════════════════════════════════════════
   PMAS — API Sync Layer (api.js)
   Connects the patient app to the backend.
   Online: syncs to server. Offline: uses localStorage fallback.
   This is the bridge between offline-first and cloud-connected.
   ═══════════════════════════════════════════════════════════════ */

const API = {
  BASE_URL: null,  // Set on init — e.g. https://api.pmas.app
  token: null,
  isOnline: navigator.onLine,

  /* Initialize — load saved token, set base URL */
  init(baseUrl) {
    this.BASE_URL = baseUrl || localStorage.getItem('pmas_api_url');
    this.token = localStorage.getItem('pmas_auth_token');
    
    // Listen for connectivity changes
    window.addEventListener('online', () => {
      this.isOnline = true;
      this.syncPending();
    });
    window.addEventListener('offline', () => {
      this.isOnline = false;
    });
  },

  /* Check if user is authenticated */
  isAuthenticated() {
    return !!this.token;
  },

  /* ── Auth ──────────────────────────────────────────────── */

  async register(phone, password, language = 'en') {
    const res = await this._fetch('/api/v1/auth/register', {
      method: 'POST',
      body: { phone_number: phone, password, role: 'patient', preferred_language: language }
    });
    if (res.access_token) {
      this.token = res.access_token;
      localStorage.setItem('pmas_auth_token', this.token);
    }
    return res;
  },

  async login(phone, password) {
    const res = await this._fetch('/api/v1/auth/login', {
      method: 'POST',
      body: { phone_number: phone, password }
    });
    if (res.access_token) {
      this.token = res.access_token;
      localStorage.setItem('pmas_auth_token', this.token);
    }
    return res;
  },

  logout() {
    this.token = null;
    localStorage.removeItem('pmas_auth_token');
    localStorage.removeItem('pmas_consent_synced');
  },

  async activate(phone, activationCode, newPassword) {
    const res = await this._fetch('/api/v1/auth/activate', {
      method: 'POST',
      body: {
        phone_number: phone,
        activation_code: activationCode,
        new_password: newPassword
      }
    });
    if (res.access_token) {
      this.token = res.access_token;
      localStorage.setItem('pmas_auth_token', this.token);
    }
    return res;
  },

  async changePassword(currentPassword, newPassword) {
    return this._fetch('/api/v1/auth/change-password', {
      method: 'POST',
      body: { current_password: currentPassword, new_password: newPassword }
    });
  },

  /* ── Profile ───────────────────────────────────────────── */

  async saveProfile(profileData) {
    return this._fetch('/api/v1/profile', {
      method: 'POST',
      body: profileData
    });
  },

  async getProfile() {
    return this._fetch('/api/v1/profile', { method: 'GET' });
  },

  /* ── Medications ──────────────────────────────────────── */

  async getMedications() {
    return this._fetch('/api/v1/medications', { method: 'GET' });
  },

  async addMedication(medData) {
    return this._fetch('/api/v1/medications', {
      method: 'POST',
      body: medData
    });
  },

  async deleteMedication(medId) {
    return this._fetch('/api/v1/medications/' + medId, { method: 'DELETE' });
  },

  /* ── Adherence ─────────────────────────────────────────── */

  async recordAdherence(medId, doseDate, slot, status) {
    // Always save to localStorage immediately (offline-first)
    const localKey = 'pmas_adherence';
    let records = JSON.parse(localStorage.getItem(localKey) || '[]');
    const idx = records.findIndex(r =>
      r.med_id === medId && r.date === doseDate && r.slot === slot
    );
    const entry = { med_id: medId, date: doseDate, slot, status, ts: new Date().toISOString() };
    if (idx >= 0) records[idx] = entry;
    else records.push(entry);
    localStorage.setItem(localKey, JSON.stringify(records));

    // Try to sync to server
    if (this.isOnline && this.token) {
      try {
        return await this._fetch('/api/v1/adherence', {
          method: 'POST',
          body: {
            medication_id: medId,
            dose_date: doseDate,
            dose_slot: slot,
            status: status
          }
        });
      } catch (e) {
        // Network failed — data is safe in localStorage, will sync later
        console.warn('Adherence sync failed, saved locally:', e);
      }
    }
    return { status: 'saved_locally' };
  },

  async getTodayAdherence() {
    if (this.isOnline && this.token) {
      return this._fetch('/api/v1/adherence/today', { method: 'GET' });
    }
    // Offline fallback — calculate from localStorage
    return this._localTodayAdherence();
  },

  async getWeeklyAdherence() {
    if (this.isOnline && this.token) {
      return this._fetch('/api/v1/adherence/weekly', { method: 'GET' });
    }
    return this._localWeeklyAdherence();
  },

  /* ── Symptoms ───────────────────────────────────────────── */

  async recordSymptom(symptomData) {
    // Save locally first
    const localKey = 'pmas_symptoms';
    let records = JSON.parse(localStorage.getItem(localKey) || '[]');
    records.push({ ...symptomData, id: 'sym_' + Date.now(), date: symptomData.log_date });
    localStorage.setItem(localKey, JSON.stringify(records));

    // Sync to server
    if (this.isOnline && this.token) {
      try {
        return await this._fetch('/api/v1/telemetry/symptom', {
          method: 'POST',
          body: symptomData
        });
      } catch (e) {
        console.warn('Symptom sync failed, saved locally:', e);
      }
    }
    return { status: 'saved_locally' };
  },

  /* ── Appointments ──────────────────────────────────────── */

  async getAppointments() {
    return this._fetch('/api/v1/appointments', { method: 'GET' });
  },

  async addAppointment(apptData) {
    return this._fetch('/api/v1/appointments', {
      method: 'POST',
      body: apptData
    });
  },

  /* ── Research Export ───────────────────────────────────── */

  async getResearchExport() {
    return this._fetch('/api/v1/research/export', { method: 'GET' });
  },

  /* ── Sync pending data when back online ────────────────── */

  /* Map local medication records to server IDs, creating each medication on
     the server on first sync. Returns true when every medication is mapped. */
  async _ensureMedicationsSynced() {
    const meds = JSON.parse(localStorage.getItem('pmas_medications') || '[]');
    let allOk = true;
    for (const med of meds) {
      if (med.server_id) continue;
      try {
        const res = await this._fetch('/api/v1/medications', {
          method: 'POST',
          body: {
            medicine_name: med.name,
            dosage: med.dose,
            frequency_morning: !!med.morning,
            frequency_afternoon: !!med.afternoon,
            frequency_night: !!med.night,
            morning_time: med.morning ? (med.morning_time || null) : null,
            afternoon_time: med.afternoon ? (med.afternoon_time || null) : null,
            night_time: med.night ? (med.night_time || null) : null,
            start_date: med.start_date,
            end_date: med.end_date,
            instructions_localized: med.notes || null
          }
        });
        med.server_id = res.id;
      } catch (e) {
        // The medication may already exist server-side (e.g. local storage was
        // cleared while the server copy remains). Match by name + dose.
        try {
          const serverMeds = await this._fetch('/api/v1/medications', { method: 'GET' });
          const match = serverMeds.find(m => m.medicine_name === med.name && m.dosage === med.dose);
          if (match) { med.server_id = match.id; }
          else { allOk = false; }
        } catch (e2) { allOk = false; }
      }
    }
    localStorage.setItem('pmas_medications', JSON.stringify(meds));
    return allOk;
  },

  /* Push the local profile + the on-device consent record to the server (§4A:
     the patient consents on their own device; the app attests it on sync). */
  async _syncProfileAndConsent() {
    if (localStorage.getItem('pmas_consent_synced') === 'true') return true;
    const profile = JSON.parse(localStorage.getItem('pmas_profile') || 'null');
    const consent = JSON.parse(localStorage.getItem('pmas_consent') || 'null');
    if (!profile || !consent) return true; // nothing to attest yet
    try {
      await this._fetch('/api/v1/profile', {
        method: 'POST',
        body: {
          full_name: profile.name,
          date_of_birth: profile.dob || null,
          gender: profile.gender || null,
          blood_group: profile.blood || null,
          known_allergies: profile.allergy || null,
          chronic_conditions: profile.chronic || null,
          emergency_contact_name: profile.emerg_name || null,
          emergency_contact_phone: profile.emerg_phone || null,
          consent_timestamp: consent.timestamp,
          consent_version: consent.version || '1.0',
          consent_checks: consent.checks || null,
          consent_status: true
        }
      });
      localStorage.setItem('pmas_consent_synced', 'true');
      return true;
    } catch (e) { return false; }
  },

  async syncPending() {
    if (!this.token) return { failed: 0 };
    console.log('PMAS: Syncing pending data...');
    let failed = 0;

    // 1. Profile + consent (pushed once per profile change)
    if (!await this._syncProfileAndConsent()) failed++;

    // 2. Medications — must map to server IDs before adherence can sync
    const medsOk = await this._ensureMedicationsSynced();
    const medMap = {};
    JSON.parse(localStorage.getItem('pmas_medications') || '[]').forEach(m => { if (m.server_id) medMap[m.id] = m.server_id; });

    // 3. Adherence — only records never synced (or whose status changed)
    const adhRecords = JSON.parse(localStorage.getItem('pmas_adherence') || '[]');
    for (const record of adhRecords) {
      if (record.synced_status === record.status) continue;
      const serverMedId = medMap[record.med_id];
      if (!serverMedId) { if (medsOk) failed++; continue; }
      try {
        await this._fetch('/api/v1/adherence', {
          method: 'POST',
          body: {
            medication_id: serverMedId,
            dose_date: record.date,
            dose_slot: record.slot,
            status: record.status
          }
        });
        record.synced_status = record.status;
      } catch (e) {
        failed++;
        break; // Stop if server is unreachable
      }
    }
    localStorage.setItem('pmas_adherence', JSON.stringify(adhRecords));

    // 4. Symptoms — only records not yet synced (prevents duplicate server rows)
    const symRecords = JSON.parse(localStorage.getItem('pmas_symptoms') || '[]');
    for (const sym of symRecords) {
      if (sym.synced) continue;
      try {
        await this._fetch('/api/v1/telemetry/symptom', {
          method: 'POST',
          body: {
            log_date: sym.date,
            pain_score: sym.pain || 0,
            systolic_bp: sym.bp_sys || null,
            diastolic_bp: sym.bp_dia || null,
            temperature: sym.temp || null,
            weight_kg: sym.weight || null,
            symptoms_observed: sym.symptoms || null,
            side_effects: sym.side_effects || null,
            additional_notes: sym.notes || null
          }
        });
        sym.synced = true;
      } catch (e) {
        failed++;
        break;
      }
    }
    localStorage.setItem('pmas_symptoms', JSON.stringify(symRecords));

    console.log('PMAS: Sync complete — failed:', failed);
    return { failed };
  },

  /* ── Internal fetch wrapper ────────────────────────────── */

  async _fetch(endpoint, options = {}) {
    if (!this.BASE_URL) {
      throw new Error('API base URL not set. Call API.init() first.');
    }

    const url = this.BASE_URL + endpoint;
    const headers = { 'Content-Type': 'application/json' };

    if (this.token) {
      headers['Authorization'] = 'Bearer ' + this.token;
    }

    const config = {
      method: options.method || 'GET',
      headers,
    };

    if (options.body) {
      config.body = JSON.stringify(options.body);
    }

    const response = await fetch(url, config);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'API request failed');
    }

    return data;
  },

  /* ── Local fallback calculations ──────────────────────── */

  _localTodayAdherence() {
    const today = new Date().toISOString().split('T')[0];
    const meds = JSON.parse(localStorage.getItem('pmas_medications') || '[]');
    const records = JSON.parse(localStorage.getItem('pmas_adherence') || '[]')
      .filter(r => r.date === today);

    let scheduled = 0, taken = 0;
    meds.forEach(m => {
      if (m.morning) scheduled++;
      if (m.afternoon) scheduled++;
      if (m.night) scheduled++;
    });
    taken = records.filter(r => r.status === 'taken').length;

    return {
      total_scheduled: scheduled,
      total_taken: taken,
      adherence_pct: scheduled > 0 ? Math.round((taken / scheduled) * 100) : 0
    };
  },

  _localWeeklyAdherence() {
    const today = new Date();
    let scheduled = 0, taken = 0;
    const meds = JSON.parse(localStorage.getItem('pmas_medications') || '[]');
    const records = JSON.parse(localStorage.getItem('pmas_adherence') || '[]');

    for (let i = 0; i < 7; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const dateStr = d.toISOString().split('T')[0];
      const dayRecords = records.filter(r => r.date === dateStr);
      meds.forEach(m => {
        if (m.morning) scheduled++;
        if (m.afternoon) scheduled++;
        if (m.night) scheduled++;
      });
      taken += dayRecords.filter(r => r.status === 'taken').length;
    }

    return {
      total_scheduled: scheduled,
      total_taken: taken,
      adherence_pct: scheduled > 0 ? Math.round((taken / scheduled) * 100) : 0
    };
  }
};
