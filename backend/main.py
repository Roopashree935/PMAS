"""
PMAS — FastAPI Backend Server
Multilingual Transition-of-Care & Clinical Adherence Engine
Dual-Vault architecture: Vault A (PII) | Vault B (Clinical & HEOR)
"""
import os
from datetime import date, datetime, timezone, timedelta
from uuid import uuid4, UUID
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, Base, engine, async_session, User, UserRole, PatientProfile, MedicationPlan, AdherenceRecord, DoseStatus, SymptomTelemetry, Appointment, SecurityAuditTrail, StudyMetadata
from schemas import (
    UserRegister, UserLogin, TokenResponse,
    PatientProfileCreate, PatientProfileResponse,
    MedicationPlanCreate, MedicationPlanResponse,
    AdherenceRecordCreate, AdherenceRecordResponse, AdherenceSummary,
    SymptomLogCreate, SymptomLogResponse, SymptomResponse,
    AppointmentCreate, AppointmentResponse,
    PatientEnrollment, PharmacistDashboard,
    AdminUserCreate, AdminUserUpdate, AdminUserResponse,
    EnrollmentResponse, PasswordChange
)
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_pharmacist_or_admin, require_admin
)

from dotenv import load_dotenv
load_dotenv()


# ─── Lifespan: configuration guard + table creation ──────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    """Refuse to start with unsafe configuration, then create tables."""
    if not os.getenv("JWT_SECRET"):
        raise RuntimeError("JWT_SECRET is not set — refusing to start with an insecure default.")
    cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    if not cors_origins:
        raise RuntimeError("CORS_ORIGINS must be set to an explicit origin allow-list.")
    if "*" in cors_origins:
        raise RuntimeError("CORS_ORIGINS must not contain '*' (wildcard origins are unsafe with credentials).")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # First-run admin bootstrap: if no admin account exists and credentials
    # are provided via environment, create the initial administrator.
    admin_phone = os.getenv("ADMIN_PHONE")
    admin_password = os.getenv("ADMIN_PASSWORD")
    if admin_phone and admin_password:
        async with async_session() as db:
            result = await db.execute(select(User).where(User.role == UserRole.admin))
            if not result.scalars().first():
                db.add(User(
                    phone_number=admin_phone,
                    password_hash=hash_password(admin_password),
                    role=UserRole.admin
                ))
                await db.commit()
    yield


app = FastAPI(
    title="PMAS API",
    description="Pharmacist-led Medication & Adherence Support — patient app, cloud sync and governance API.",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# ─── CORS ────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════
# HEALTH & SYSTEM
# ═══════════════════════════════════════════════════════════════

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ACTIVE", "system": "PMAS Cloud Core", "privacy_posture": "dpdp_aligned_design"}



# ═══════════════════════════════════════════════════════════════
# AUTHENTICATION
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/auth/register", response_model=TokenResponse)
async def register(user_data: UserRegister, request: Request, db: AsyncSession = Depends(get_db)):
    """Register a new patient account.

    Self-registration is patient-only; the role field is not accepted.
    Staff (pharmacist/admin) accounts are created by an administrator.
    """
    existing = await db.execute(select(User).where(User.phone_number == user_data.phone_number))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Phone number already registered")

    user = User(
        phone_number=user_data.phone_number,
        password_hash=hash_password(user_data.password),
        role=UserRole.patient,
        preferred_language=user_data.preferred_language
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Phone number already registered")

    # Assign Study ID for patients
    if user.role == UserRole.patient:
        study_meta = StudyMetadata(
            user_id=user.id,
            study_id=f"PMAS-{str(uuid4().int)[:6]}",
            baseline_date=date.today()
        )
        db.add(study_meta)

    # Audit
    db.add(SecurityAuditTrail(performed_by=user.id, action="REGISTER", target_resource="users", ip_address=request.client.host if request.client else None))

    token = create_access_token(user.id, user.role.value)
    return TokenResponse(access_token=token, role=user.role.value, user_id=str(user.id))


# ─── Login throttling (in-process, per phone; reset on success) ──
_failed_logins: dict = {}
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_MINUTES = 15


def _register_failed_login(phone: str):
    entry = _failed_logins.get(phone, {"count": 0, "locked_until": None})
    entry["count"] += 1
    if entry["count"] >= LOGIN_MAX_FAILURES:
        entry["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        entry["count"] = 0
    _failed_logins[phone] = entry


@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    """Login with phone number and password. Locks out after repeated failures."""
    phone = credentials.phone_number
    entry = _failed_logins.get(phone)
    if entry and entry["locked_until"] and datetime.now(timezone.utc) < entry["locked_until"]:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")

    result = await db.execute(select(User).where(User.phone_number == phone))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.password_hash):
        _register_failed_login(phone)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    _failed_logins.pop(phone, None)

    # Audit
    db.add(SecurityAuditTrail(performed_by=user.id, action="LOGIN", target_resource="auth", ip_address=request.client.host if request.client else None))

    token = create_access_token(user.id, user.role.value)
    return TokenResponse(access_token=token, role=user.role.value, user_id=str(user.id))


@app.post("/api/v1/auth/change-password")
async def change_password(
    data: PasswordChange,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Change the current user's password (enrolled patients use this on first login)."""
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    db.add(SecurityAuditTrail(performed_by=user.id, action="PASSWORD_CHANGE", target_resource="auth"))
    return {"status": "changed"}


# ═══════════════════════════════════════════════════════════════
# PATIENT PROFILE (Vault A)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/profile", response_model=PatientProfileResponse)
async def create_profile(
    profile_data: PatientProfileCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create or update the patient profile (patient accounts only)."""
    if user.role != UserRole.patient:
        raise HTTPException(status_code=403, detail="Only patient accounts may hold a patient profile")
    existing = await db.execute(select(PatientProfile).where(PatientProfile.user_id == user.id))
    profile = existing.scalar_one_or_none()

    if profile:
        # Update existing
        for key, val in profile_data.dict().items():
            setattr(profile, key, val)
    else:
        profile = PatientProfile(user_id=user.id, **profile_data.dict())
        db.add(profile)

    db.add(SecurityAuditTrail(performed_by=user.id, action="PROFILE_UPDATE", target_resource="patient_profiles"))
    await db.flush()
    return profile


@app.get("/api/v1/profile", response_model=PatientProfileResponse)
async def get_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's profile."""
    result = await db.execute(select(PatientProfile).where(PatientProfile.user_id == user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


# ═══════════════════════════════════════════════════════════════
# MEDICATIONS (Vault B)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/medications", response_model=MedicationPlanResponse)
async def create_medication(
    med_data: MedicationPlanCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a medication to the patient's regimen."""
    med = MedicationPlan(
        patient_id=user.id,
        prescribed_by=user.id,  # Self-prescribed by patient; pharmacist uses portal
        **med_data.dict()
    )
    db.add(med)
    db.add(SecurityAuditTrail(performed_by=user.id, action="MEDICATION_ADD", target_resource="medication_plans"))
    await db.flush()
    return med


@app.get("/api/v1/medications", response_model=List[MedicationPlanResponse])
async def get_medications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    active_only: bool = Query(default=False)
):
    """Get all medications for the current patient."""
    query = select(MedicationPlan).where(MedicationPlan.patient_id == user.id)
    if active_only:
        query = query.where(MedicationPlan.is_active == True)
    result = await db.execute(query.order_by(MedicationPlan.created_at.desc()))
    return result.scalars().all()


@app.delete("/api/v1/medications/{med_id}")
async def delete_medication(
    med_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Soft-delete a medication (mark as inactive)."""
    result = await db.execute(select(MedicationPlan).where(MedicationPlan.id == med_id))
    med = result.scalar_one_or_none()
    if not med or med.patient_id != user.id:
        raise HTTPException(status_code=404, detail="Medication not found")
    med.is_active = False
    db.add(SecurityAuditTrail(performed_by=user.id, action="MEDICATION_DELETE", target_resource="medication_plans"))
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════════
# ADHERENCE TRACKING (Vault B — PRIMARY OUTCOME)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/adherence", response_model=AdherenceRecordResponse)
async def record_adherence(
    record_data: AdherenceRecordCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Record a dose as taken, delayed, or missed."""
    # The medication must belong to the authenticated patient
    med_result = await db.execute(
        select(MedicationPlan).where(
            MedicationPlan.id == record_data.medication_id,
            MedicationPlan.patient_id == user.id
        )
    )
    if not med_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Medication not found")

    # Dose date may not be more than one day in the future (timezone tolerance)
    if record_data.dose_date > date.today() + timedelta(days=1):
        raise HTTPException(status_code=422, detail="Dose date cannot be in the future")

    # Check if already exists (upsert)
    existing = await db.execute(
        select(AdherenceRecord).where(
            and_(
                AdherenceRecord.patient_id == user.id,
                AdherenceRecord.medication_id == record_data.medication_id,
                AdherenceRecord.dose_date == record_data.dose_date,
                AdherenceRecord.dose_slot == record_data.dose_slot
            )
        )
    )
    record = existing.scalar_one_or_none()

    if record:
        record.status = DoseStatus(record_data.status)
    else:
        record = AdherenceRecord(
            patient_id=user.id,
            medication_id=record_data.medication_id,
            dose_date=record_data.dose_date,
            dose_slot=record_data.dose_slot,
            status=DoseStatus(record_data.status)
        )
        db.add(record)

    await db.flush()
    return record


@app.get("/api/v1/adherence/today", response_model=AdherenceSummary)
async def get_today_adherence(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get today's adherence summary for the current patient."""
    today = date.today()
    meds_result = await db.execute(
        select(MedicationPlan).where(
            and_(
                MedicationPlan.patient_id == user.id,
                MedicationPlan.is_active == True,
                MedicationPlan.start_date <= today,
                MedicationPlan.end_date >= today
            )
        )
    )
    meds = meds_result.scalars().all()

    total_scheduled = 0
    for m in meds:
        if m.frequency_morning: total_scheduled += 1
        if m.frequency_afternoon: total_scheduled += 1
        if m.frequency_night: total_scheduled += 1

    records_result = await db.execute(
        select(AdherenceRecord).where(
            and_(AdherenceRecord.patient_id == user.id, AdherenceRecord.dose_date == today)
        )
    )
    records = records_result.scalars().all()
    total_taken = sum(1 for r in records if r.status == DoseStatus.taken)

    return AdherenceSummary(
        total_scheduled=total_scheduled,
        total_taken=total_taken,
        adherence_pct=round((total_taken / total_scheduled * 100), 1) if total_scheduled > 0 else 0
    )


@app.get("/api/v1/adherence/weekly", response_model=AdherenceSummary)
async def get_weekly_adherence(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get weekly adherence summary (last 7 days)."""
    today = date.today()
    start = today - timedelta(days=6)

    meds_result = await db.execute(
        select(MedicationPlan).where(MedicationPlan.patient_id == user.id)
    )
    meds = meds_result.scalars().all()

    total_scheduled = 0
    total_taken = 0

    for i in range(7):
        d = today - timedelta(days=i)
        active_meds = [m for m in meds if m.start_date <= d and m.end_date >= d]
        for m in active_meds:
            if m.frequency_morning: total_scheduled += 1
            if m.frequency_afternoon: total_scheduled += 1
            if m.frequency_night: total_scheduled += 1

    records_result = await db.execute(
        select(AdherenceRecord).where(
            and_(
                AdherenceRecord.patient_id == user.id,
                AdherenceRecord.dose_date >= start,
                AdherenceRecord.dose_date <= today
            )
        )
    )
    records = records_result.scalars().all()
    total_taken = sum(1 for r in records if r.status == DoseStatus.taken)

    return AdherenceSummary(
        total_scheduled=total_scheduled,
        total_taken=total_taken,
        adherence_pct=round((total_taken / total_scheduled * 100), 1) if total_scheduled > 0 else 0
    )


# ═══════════════════════════════════════════════════════════════
# SYMPTOM TELEMETRY (Vault B)
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/telemetry/symptom", response_model=SymptomResponse)
async def record_symptom(
    log: SymptomLogCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Record a symptom telemetry entry with ICMR safety engine."""
    red_flag = False
    action_msg = None

    # Safety escalation — not diagnosis
    if log.pain_score >= 8 or (log.systolic_bp and log.systolic_bp >= 180):
        red_flag = True
        action_msg = "SAFETY ESCALATION: This reading may require urgent medical attention. Please seek professional evaluation."

    symptom = SymptomTelemetry(
        patient_id=user.id,
        log_date=log.log_date,
        pain_score=log.pain_score,
        systolic_bp=log.systolic_bp,
        diastolic_bp=log.diastolic_bp,
        temperature=log.temperature,
        weight_kg=log.weight_kg,
        symptoms_observed=log.symptoms_observed,
        side_effects=log.side_effects,
        additional_notes=log.additional_notes,
        red_flag_triggered=red_flag
    )
    db.add(symptom)
    db.add(SecurityAuditTrail(performed_by=user.id, action="SYMPTOM_LOG", target_resource="symptom_telemetry"))

    return SymptomResponse(status="SUCCESS", red_flag_alert=red_flag, action_required=action_msg)


@app.get("/api/v1/telemetry/symptoms", response_model=List[SymptomLogResponse])
async def get_symptoms(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=200)
):
    """Get symptom logs for the current patient."""
    result = await db.execute(
        select(SymptomTelemetry)
        .where(SymptomTelemetry.patient_id == user.id)
        .order_by(SymptomTelemetry.log_date.desc())
        .limit(limit)
    )
    return result.scalars().all()


# ═══════════════════════════════════════════════════════════════
# APPOINTMENTS
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/appointments", response_model=AppointmentResponse)
async def create_appointment(
    appt_data: AppointmentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new appointment."""
    appt = Appointment(patient_id=user.id, **appt_data.dict())
    db.add(appt)
    await db.flush()
    return appt


@app.get("/api/v1/appointments", response_model=List[AppointmentResponse])
async def get_appointments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    upcoming_only: bool = Query(default=False)
):
    """Get appointments for the current patient."""
    query = select(Appointment).where(Appointment.patient_id == user.id)
    if upcoming_only:
        query = query.where(Appointment.appointment_date >= date.today())
    result = await db.execute(query.order_by(Appointment.appointment_date.desc()))
    return result.scalars().all()


# ═══════════════════════════════════════════════════════════════
# PHARMACIST PORTAL — Patient Enrollment & Management
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/pharmacist/enroll", response_model=EnrollmentResponse)
async def enroll_patient(
    enrollment: PatientEnrollment,
    request: Request,
    pharmacist: User = Depends(require_pharmacist_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """Pharmacist enrolls a new patient — creates account and profile.

    Returns a one-time temporary password that the pharmacist must relay to
    the patient; the patient changes it at first login. Consent is NOT granted
    here: the patient consents on their own device (PRD v1.1 §4A) and the
    patient app attests the consent record when it first syncs.
    """
    existing = await db.execute(select(User).where(User.phone_number == enrollment.phone_number))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Patient already enrolled")

    temp_password = str(uuid4().int)[:8]
    user = User(
        phone_number=enrollment.phone_number,
        password_hash=hash_password(temp_password),
        role=UserRole.patient,
        preferred_language=enrollment.preferred_language
    )
    db.add(user)
    await db.flush()

    profile = PatientProfile(
        user_id=user.id,
        full_name=enrollment.full_name,
        hospital_mrn=enrollment.hospital_mrn,
        emergency_contact_name=enrollment.emergency_contact_name,
        emergency_contact_phone=enrollment.emergency_contact_phone,
        date_of_birth=enrollment.date_of_birth,
        gender=enrollment.gender,
        blood_group=enrollment.blood_group,
        known_allergies=enrollment.known_allergies,
        chronic_conditions=enrollment.chronic_conditions,
        consent_timestamp=datetime.now(timezone.utc),
        consent_version="1.0",
        consent_status=False  # pending: patient consents on-device (§4A) and attests on first sync
    )
    db.add(profile)

    study_meta = StudyMetadata(
        user_id=user.id,
        study_id=f"PMAS-{str(uuid4().int)[:6]}",
        baseline_date=date.today()
    )
    db.add(study_meta)

    db.add(SecurityAuditTrail(
        performed_by=pharmacist.id,
        action="PATIENT_ENROLLED",
        target_resource=f"users:{user.id}",
        ip_address=request.client.host if request.client else None
    ))

    token = create_access_token(user.id, user.role.value)
    return EnrollmentResponse(
        access_token=token,
        role=user.role.value,
        user_id=str(user.id),
        temp_password=temp_password
    )


@app.get("/api/v1/pharmacist/dashboard", response_model=PharmacistDashboard)
async def pharmacist_dashboard(
    request: Request,
    pharmacist: User = Depends(require_pharmacist_or_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard stats for pharmacist. Every access is audit-logged.

    NOTE (audit 2026-09-28): stats are currently GLOBAL. Per-pharmacist scoping
    on `patient_profiles.enrolled_by` is staged for the next release and
    requires a one-time database migration first (see migrations/002).
    """
    db.add(SecurityAuditTrail(
        performed_by=pharmacist.id,
        action="DASHBOARD_VIEW",
        target_resource="pharmacist_dashboard",
        ip_address=request.client.host if request.client else None
    ))
    total_patients = await db.scalar(
        select(func.count(User.id)).where(User.role == UserRole.patient)
    )

    active_meds = await db.scalar(
        select(func.count(MedicationPlan.id)).where(MedicationPlan.is_active == True)
    )

    today = date.today()
    adherence_records = await db.execute(
        select(AdherenceRecord).where(AdherenceRecord.dose_date == today)
    )
    records = adherence_records.scalars().all()
    taken_today = sum(1 for r in records if r.status == DoseStatus.taken)
    total_today = len(records)
    adherence_avg = round((taken_today / total_today * 100), 1) if total_today > 0 else 0

    red_flags = await db.scalar(
        select(func.count(SymptomTelemetry.id)).where(SymptomTelemetry.red_flag_triggered == True)
    )

    recent_patients_result = await db.execute(
        select(PatientProfile, User, StudyMetadata)
        .join(User, PatientProfile.user_id == User.id)
        .outerjoin(StudyMetadata, StudyMetadata.user_id == User.id)
        .where(User.role == UserRole.patient)
        .order_by(PatientProfile.created_at.desc())
        .limit(10)
    )
    recent = [
        {
            "name": p.full_name,
            "phone": u.phone_number,
            "study_id": s_.study_id if s_ else None
        }
        for p, u, s_ in recent_patients_result
    ]

    return PharmacistDashboard(
        total_patients=total_patients or 0,
        active_medications=active_meds or 0,
        today_adherence_avg=adherence_avg,
        red_flag_alerts=red_flags or 0,
        recent_patients=recent
    )


# ═══════════════════════════════════════════════════════════════
# HEOR RESEARCH EXPORT (De-identified)
# ═══════════════════════════════════════════════════════════════

@app.get("/api/v1/research/export")
async def research_export(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate a de-identified research export for HEOR analysis (self-scoped, audit-logged)."""
    study_meta = await db.execute(
        select(StudyMetadata).where(StudyMetadata.user_id == user.id)
    )
    study = study_meta.scalar_one_or_none()

    if not study:
        raise HTTPException(status_code=404, detail="Study metadata not found")

    db.add(SecurityAuditTrail(
        performed_by=user.id,
        action="RESEARCH_EXPORT",
        target_resource=f"study:{study.study_id}",
        ip_address=request.client.host if request.client else None
    ))

    study_day = (date.today() - study.baseline_date).days if study.baseline_date else 0

    # Adherence records — study_day instead of raw dates
    adh_result = await db.execute(
        select(AdherenceRecord).where(AdherenceRecord.patient_id == user.id)
    )
    adherence_records = [
        {
            "study_day": (r.dose_date - study.baseline_date).days if study.baseline_date else 0,
            "slot": r.dose_slot,
            "status": r.status.value
        }
        for r in adh_result.scalars().all()
    ]

    # Symptom telemetry — study_day, no free text
    sym_result = await db.execute(
        select(SymptomTelemetry).where(SymptomTelemetry.patient_id == user.id)
    )
    symptoms = [
        {
            "study_day": (s.log_date - study.baseline_date).days if study.baseline_date else 0,
            "pain_score": s.pain_score,
            "temp_c": s.temperature,
            "weight_kg": s.weight_kg,
            "bp_sys": s.systolic_bp,
            "bp_dia": s.diastolic_bp,
            "has_symptoms": 1 if s.symptoms_observed else 0,
            "has_side_effects": 1 if s.side_effects else 0,
            "red_flag": s.red_flag_triggered
        }
        for s in sym_result.scalars().all()
    ]

    return {
        "study": "PMAS-RESEARCH",
        "study_id": study.study_id,
        "study_day_at_export": study_day,
        "adherence": {
            "total_records": len(adherence_records),
            "records": adherence_records
        },
        "symptoms": {
            "total_logs": len(symptoms),
            "entries": symptoms
        },
        "data_governance": {
            "data_location": "cloud_postgresql",
            "pii_in_export": False,
            "uses_study_day": True,
            "raw_dates_in_export": False
        }
    }


# ═══════════════════════════════════════════════════════════════
# ADMIN — ACCOUNT GOVERNANCE
# ═══════════════════════════════════════════════════════════════

@app.get("/api/v1/admin/users", response_model=List[AdminUserResponse])
async def admin_list_users(
    role: Optional[str] = Query(None, pattern=r"^(patient|pharmacist|admin)$"),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List user accounts. Administrator only."""
    stmt = select(User).order_by(User.created_at.desc()).limit(500)
    if role:
        stmt = stmt.where(User.role == UserRole(role))
    result = await db.execute(stmt)
    return [
        AdminUserResponse(
            user_id=str(u.id),
            phone_number=u.phone_number,
            role=u.role.value,
            is_active=u.is_active,
            preferred_language=u.preferred_language,
            created_at=u.created_at
        ) for u in result.scalars().all()
    ]


@app.post("/api/v1/admin/users", response_model=AdminUserResponse, status_code=201)
async def admin_create_user(
    data: AdminUserCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a staff (pharmacist/admin) account. Administrator only; audit-logged."""
    existing = await db.execute(select(User).where(User.phone_number == data.phone_number))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Phone number already registered")

    user = User(
        phone_number=data.phone_number,
        password_hash=hash_password(data.password),
        role=UserRole(data.role),
        preferred_language=data.preferred_language
    )
    db.add(user)
    await db.flush()

    db.add(SecurityAuditTrail(
        performed_by=admin.id,
        action="ADMIN_CREATE_USER",
        target_resource=f"users:{user.id} role={user.role.value}"
    ))

    return AdminUserResponse(
        user_id=str(user.id),
        phone_number=user.phone_number,
        role=user.role.value,
        is_active=user.is_active,
        preferred_language=user.preferred_language,
        created_at=user.created_at
    )


@app.patch("/api/v1/admin/users/{user_id}", response_model=AdminUserResponse)
async def admin_update_user(
    user_id: UUID,
    data: AdminUserUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Change a user's role or suspend/reactivate the account.

    Administrator only; audit-logged. An admin cannot change their own
    role or status, so the governance account can never lock itself out.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Admins cannot change their own role or status")

    changes = []
    if data.role is not None and data.role != user.role.value:
        user.role = UserRole(data.role)
        changes.append(f"role={data.role}")
    if data.is_active is not None and data.is_active != user.is_active:
        user.is_active = data.is_active
        changes.append("suspended" if not data.is_active else "reactivated")
    if not changes:
        raise HTTPException(status_code=400, detail="Nothing to update")

    await db.flush()
    db.add(SecurityAuditTrail(
        performed_by=admin.id,
        action="ADMIN_UPDATE_USER",
        target_resource=f"users:{user.id} ({', '.join(changes)})"
    ))

    return AdminUserResponse(
        user_id=str(user.id),
        phone_number=user.phone_number,
        role=user.role.value,
        is_active=user.is_active,
        preferred_language=user.preferred_language,
        created_at=user.created_at
    )


# ═══════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )
