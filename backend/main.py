"""
PMAS — FastAPI Backend Server
Multilingual Transition-of-Care & Clinical Adherence Engine
Dual-Vault architecture: Vault A (PII) | Vault B (Clinical & HEOR)
"""
import os
import secrets
from datetime import date, datetime, timezone, timedelta
from uuid import uuid4, UUID
from zoneinfo import ZoneInfo
from typing import List, Optional

# Load environment variables BEFORE importing database/auth: both modules
# read JWT_SECRET and DATABASE_URL at import time, so importing them first
# would silently fall back to the insecure development defaults (#26).
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, and_
from sqlalchemy.exc import IntegrityError
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, Base, engine, async_session, User, UserRole, PatientProfile, MedicationPlan, AdherenceRecord, DoseStatus, SymptomTelemetry, Appointment, SecurityAuditTrail, StudyMetadata, PendingActivation, BreakGlassAccess, ThrottleState
from schemas import (
    UserRegister, UserLogin, TokenResponse,
    PatientProfileCreate, PatientProfileResponse,
    MedicationPlanCreate, MedicationPlanResponse,
    AdherenceRecordCreate, AdherenceRecordResponse, AdherenceSummary,
    SymptomLogCreate, SymptomLogResponse, SymptomResponse,
    AppointmentCreate, AppointmentResponse,
    PatientEnrollment, PharmacistDashboard,
    AdminUserCreate, AdminUserUpdate, AdminUserResponse,
    EnrollmentResponse, PasswordChange, ActivationRequest, BreakGlassRequest
)
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_pharmacist, require_admin,
    JWT_SECRET
)


# ─── Lifespan: configuration guard + table creation ──────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    """Refuse to start with unsafe configuration, then create tables."""
    if not os.getenv("JWT_SECRET"):
        raise RuntimeError("JWT_SECRET is not set — refusing to start with an insecure default.")
    # Defense in depth (#26): auth.py captures JWT_SECRET at import time, so
    # verify the effective signing secret is not the public development default.
    if JWT_SECRET == "pmas-dev-secret-change-in-production":
        raise RuntimeError(
            "JWT_SECRET resolved to the public development default — refusing to start. "
            "Set a real secret via an environment variable or .env "
            "(loaded before the auth import; see #26)."
        )
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

# ─── Fixed clinical timezone ────────────────────────────────
# All dose dates and day-scoped summaries use Asia/Kolkata, NOT the
# server's local time (UTC on Render): the IST day boundary is 05:30,
# so UTC-based dates attribute 00:00-05:30 IST doses to the previous
# day (#28). The patient app keys dates with the same fixed offset
# (see patient-app/demo/js/clinical-date.js: clinicalDateKey).
CLINICAL_TZ = ZoneInfo("Asia/Kolkata")


def clinical_today() -> date:
    """Today's date in the fixed clinical timezone (Asia/Kolkata)."""
    return datetime.now(CLINICAL_TZ).date()


def expected_dose_slots(meds, day: date) -> int:
    """Expected dose slots for a clinical day from active medication plans.

    Shared by the pharmacist dashboard and admin break-glass so both
    compute adherence against the prescribed regimen, not just logged
    doses — a patient who took 1 of 3 doses and logged only that one
    is 33%, not 100% (issue #29)."""
    total = 0
    for med in meds:
        if getattr(med, "is_active", True) and med.start_date <= day <= med.end_date:
            total += int(bool(med.frequency_morning)) + int(bool(med.frequency_afternoon)) + int(bool(med.frequency_night))
    return total


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
study_id=f"PMAS-{str(uuid4().int)[:10]}",  # 10-digit space (#31): 6 digits 50%-collide at ~1.2k patients
            baseline_date=clinical_today()
        )
        db.add(study_meta)

    # Audit
    db.add(SecurityAuditTrail(performed_by=user.id, action="REGISTER", target_resource="users", ip_address=request.client.host if request.client else None))

    token = create_access_token(user.id, user.role.value)
    return TokenResponse(access_token=token, role=user.role.value, user_id=str(user.id))


# ─── Throttling (DB-backed: survives restarts, shared across workers) ──
# Issue #27: the previous in-process dicts reset on every restart, were
# per-worker, and grew unboundedly. Limits are now persisted in the
# throttle_states table — one row per (context, phone); 5 consecutive
# failures lock that phone for 15 minutes; a success clears the row.
LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_MINUTES = 15


async def _throttle_get(db: AsyncSession, context: str, phone: str):
    return (await db.execute(
        select(ThrottleState).where(and_(
            ThrottleState.context == context, ThrottleState.phone_number == phone
        ))
    )).scalar_one_or_none()


async def _throttle_check(db: AsyncSession, context: str, phone: str):
    row = await _throttle_get(db, context, phone)
    if row and row.locked_until:
        lu = row.locked_until
        if lu.tzinfo is None:  # SQLite returns naive datetimes; Postgres is timezone-aware
            lu = lu.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < lu:
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")
        # Lockout expired — prune the row on read so the table self-cleans
        # (review §3.2: TTL pruning instead of unbounded retention).
        await db.delete(row)
        await db.commit()
        return


async def _throttle_fail(db: AsyncSession, context: str, phone: str):
    row = await _throttle_get(db, context, phone)
    if not row:
        row = ThrottleState(context=context, phone_number=phone, failed_count=0)
    row.failed_count = (row.failed_count or 0) + 1
    if row.failed_count >= LOGIN_MAX_FAILURES:
        row.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        row.failed_count = 0
    db.add(row)
    await db.commit()  # the caller raises 401/400 right after; persist now or lose it


async def _throttle_clear(db: AsyncSession, context: str, phone: str):
    row = await _throttle_get(db, context, phone)
    if row:
        await db.delete(row)
        await db.commit()



@app.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    """Login with phone number and password. Locks out after repeated failures."""
    phone = credentials.phone_number
    await _throttle_check(db, "login", phone)

    result = await db.execute(select(User).where(User.phone_number == phone))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.password_hash):
        await _throttle_fail(db, "login", phone)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        # Note: unactivated (enrolled-but-pending) accounts can never reach this branch —
        # their password hash is an unguessable placeholder, so the password check above
        # already fails with a generic 401. That is intentional: revealing "not yet
        # activated" would enumerate enrolled phone numbers.
        raise HTTPException(status_code=403, detail="Account deactivated")

    await _throttle_clear(db, "login", phone)

    # Audit
    db.add(SecurityAuditTrail(performed_by=user.id, action="LOGIN", target_resource="auth", ip_address=request.client.host if request.client else None))

    token = create_access_token(user.id, user.role.value)
    return TokenResponse(access_token=token, role=user.role.value, user_id=str(user.id))


@app.post("/api/v1/auth/activate", response_model=TokenResponse)
async def activate_account(
    data: ActivationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Patient activates an account created by pharmacist enrollment.

    The pharmacist never sets or sees the patient's password: enrollment
    issues a one-time activation code (valid 7 days); the patient chooses
    their own password here, on their own device (PRD v1.1 §4A / G8)."""
    phone = data.phone_number
    await _throttle_check(db, "activation", phone)

    result = await db.execute(select(User).where(User.phone_number == phone))
    user = result.scalar_one_or_none()
    pending = None
    if user:
        p_result = await db.execute(
            select(PendingActivation).where(PendingActivation.user_id == user.id)
        )
        pending = p_result.scalar_one_or_none()

    if not user or not pending or not verify_password(data.activation_code, pending.code_hash):
        await _throttle_fail(db, "activation", phone)
        raise HTTPException(status_code=400, detail="Invalid phone number or activation code")

    expires_at = pending.expires_at
    if expires_at.tzinfo is None:  # SQLite returns naive datetimes; Postgres is timezone-aware
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=410, detail="Activation code expired. Ask your pharmacist to re-enroll you.")

    user.password_hash = hash_password(data.new_password)
    user.is_active = True
    await db.delete(pending)
    await _throttle_clear(db, "activation", phone)
    db.add(SecurityAuditTrail(
        performed_by=user.id, action="ACCOUNT_ACTIVATED", target_resource="auth",
        ip_address=request.client.host if request.client else None
    ))
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
    med_id: UUID,  # UUID-typed: non-UUID input is a 422, not a 500 (#33)
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
    if record_data.dose_date > clinical_today() + timedelta(days=1):
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
    today = clinical_today()
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
    today = clinical_today()
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
        query = query.where(Appointment.appointment_date >= clinical_today())
    result = await db.execute(query.order_by(Appointment.appointment_date.desc()))
    return result.scalars().all()


# ═══════════════════════════════════════════════════════════════
# PHARMACIST PORTAL — Patient Enrollment & Management
# ═══════════════════════════════════════════════════════════════

@app.post("/api/v1/pharmacist/enroll", response_model=EnrollmentResponse)
async def enroll_patient(
    enrollment: PatientEnrollment,
    request: Request,
    pharmacist: User = Depends(require_pharmacist),
    db: AsyncSession = Depends(get_db)
):
    """Pharmacist enrolls a new patient — creates an INACTIVE account and profile.

    Returns a one-time activation code (valid 7 days) that the pharmacist
    relays to the patient. The patient activates the account on their own
    device and chooses their own password — the pharmacist never enters,
    receives, or sees the patient's password (PRD v1.1 §4A / G8).
    Consent is NOT granted here: the patient consents on their own device
    and the patient app attests the consent record when it first syncs.
    """
    existing = await db.execute(select(User).where(User.phone_number == enrollment.phone_number))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Patient already enrolled")

    # Random, unguessable placeholder hash: the account is INACTIVE until the
    # patient activates it with their own chosen password.
    user = User(
        phone_number=enrollment.phone_number,
        password_hash=hash_password(secrets.token_hex(16)),
        role=UserRole.patient,
        is_active=False,
        preferred_language=enrollment.preferred_language
    )
    db.add(user)
    await db.flush()

    activation_code = f"{secrets.randbelow(1000000):06d}"
    db.add(PendingActivation(
        user_id=user.id,
        code_hash=hash_password(activation_code),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)
    ))

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
        consent_timestamp=None,  # G10: no consent has occurred yet; set at attestation
        consent_version="1.0",
        consent_status=False,  # pending: patient consents on-device (§4A) and attests on first sync
        enrolled_by=pharmacist.id
    )
    db.add(profile)

    study_meta = StudyMetadata(
        user_id=user.id,
study_id=f"PMAS-{str(uuid4().int)[:10]}",  # 10-digit space (#31): 6 digits 50%-collide at ~1.2k patients
        baseline_date=clinical_today()
    )
    db.add(study_meta)

    db.add(SecurityAuditTrail(
        performed_by=pharmacist.id,
        action="PATIENT_ENROLLED",
        target_resource=f"users:{user.id}",
        ip_address=request.client.host if request.client else None
    ))

    return EnrollmentResponse(
        user_id=str(user.id),
        role=user.role.value,
        study_id=study_meta.study_id if study_meta else None,
        activation_code=activation_code,
        activation_expires_days=7
    )


@app.get("/api/v1/pharmacist/dashboard", response_model=PharmacistDashboard)
async def pharmacist_dashboard(
    request: Request,
    pharmacist: User = Depends(require_pharmacist),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard stats, scoped to patients this pharmacist personally
    enrolled (permission matrix: a pharmacist sees only their own patients).
    Pharmacist-only by design: admin is a governance role and reaches clinical
    data exclusively through the break-glass route (G9). Every access is
    audit-logged. Self-registered patients are not visible to any pharmacist
    until enrolled.
    """
    db.add(SecurityAuditTrail(
        performed_by=pharmacist.id,
        action="DASHBOARD_VIEW",
        target_resource="pharmacist_dashboard",
        ip_address=request.client.host if request.client else None
    ))
    my_patient_ids = select(PatientProfile.user_id).where(
        PatientProfile.enrolled_by == pharmacist.id
    )

    total_patients = await db.scalar(
        select(func.count(PatientProfile.id)).where(
            PatientProfile.enrolled_by == pharmacist.id
        )
    )

    active_meds = await db.scalar(
        select(func.count(MedicationPlan.id)).where(
            MedicationPlan.is_active == True,
            MedicationPlan.patient_id.in_(my_patient_ids)
        )
    )

    today = clinical_today()
    adherence_records = await db.execute(
        select(AdherenceRecord).where(
            AdherenceRecord.dose_date == today,
            AdherenceRecord.patient_id.in_(my_patient_ids)
        )
    )
    records = adherence_records.scalars().all()
    taken_today = sum(1 for r in records if r.status == DoseStatus.taken)
    # Expected slots from ACTIVE plans, not just logged doses (#29): the
    # pharmacist makes intervention decisions from this number, so a
    # patient who took 1 of 3 doses and logged only that one is 33%, not 100%.
    active_meds_today = (await db.execute(
        select(MedicationPlan).where(and_(
            MedicationPlan.patient_id.in_(my_patient_ids),
            MedicationPlan.is_active == True
        ))
    )).scalars().all()
    expected_today = expected_dose_slots(active_meds_today, today)
    adherence_avg = round((taken_today / expected_today * 100), 1) if expected_today > 0 else 0

    red_flags = await db.scalar(
        select(func.count(SymptomTelemetry.id)).where(
            SymptomTelemetry.red_flag_triggered == True,
            SymptomTelemetry.patient_id.in_(my_patient_ids)
        )
    )

    recent_patients_result = await db.execute(
        select(PatientProfile, User, StudyMetadata)
        .join(User, PatientProfile.user_id == User.id)
        .outerjoin(StudyMetadata, StudyMetadata.user_id == User.id)
        .where(PatientProfile.enrolled_by == pharmacist.id)
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
    """Generate a de-identified research export for HEOR analysis.

    Gated on the patient's ATTESTED research consent (G5): authentication is
    not authorization, audit logging is not authorization, and de-identification
    is not authorization. The consent record must show consent_status=True
    with the full set of research-consent acknowledgements (§4A attestation).
    """
    study_meta = await db.execute(
        select(StudyMetadata).where(StudyMetadata.user_id == user.id)
    )
    study = study_meta.scalar_one_or_none()

    if not study:
        raise HTTPException(status_code=404, detail="Study metadata not found")

    profile_result = await db.execute(
        select(PatientProfile).where(PatientProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()
    checks = profile.consent_checks if profile else None
    consent_valid = (
        profile is not None
        and profile.consent_status is True
        and (
            (isinstance(checks, list) and len(checks) >= 5 and all(checks))
            or (isinstance(checks, dict) and bool(checks))
        )
    )
    if not consent_valid:
        raise HTTPException(
            status_code=403,
            detail="Research export requires the patient's attested research consent"
        )

    db.add(SecurityAuditTrail(
        performed_by=user.id,
        action="RESEARCH_EXPORT",
        target_resource=f"study:{study.study_id}",
        ip_address=request.client.host if request.client else None
    ))

    study_day = (clinical_today() - study.baseline_date).days if study.baseline_date else 0

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

@app.post("/api/v1/admin/break-glass")
async def admin_break_glass(
    data: BreakGlassRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Exceptional admin access to ONE patient's clinical data (G9).

    Admin is a governance role: routine clinical access is pharmacist-only.
    Every break-glass use requires a written reason, which is persisted
    (break_glass_access table) and audit-logged with the caller's IP.
    """
    if len(data.reason.strip()) < 10:
        raise HTTPException(status_code=422, detail="A written reason (at least 10 characters) is required")

    result = await db.execute(select(User).where(User.phone_number == data.phone_number))
    patient = result.scalar_one_or_none()
    if not patient or patient.role != UserRole.patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    profile_result = await db.execute(
        select(PatientProfile).where(PatientProfile.user_id == patient.id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Patient has no profile on record")

    study_result = await db.execute(
        select(StudyMetadata).where(StudyMetadata.user_id == patient.id)
    )
    study = study_result.scalar_one_or_none()

    meds = (await db.execute(
        select(MedicationPlan).where(MedicationPlan.patient_id == patient.id)
    )).scalars().all()

    today = clinical_today()
    # One range query instead of one query per day (N+1, issue #32);
    # expected slots from the shared helper, same as the dashboard (#29).
    week_records = (await db.execute(
        select(AdherenceRecord).where(and_(
            AdherenceRecord.patient_id == patient.id,
            AdherenceRecord.dose_date.between(today - timedelta(days=6), today)
        ))
    )).scalars().all()
    taken = sum(1 for r in week_records if r.status == DoseStatus.taken)
    expected_slots = sum(expected_dose_slots(meds, today - timedelta(days=i)) for i in range(7))

    red_flags = await db.scalar(
        select(func.count(SymptomTelemetry.id)).where(
            and_(SymptomTelemetry.patient_id == patient.id, SymptomTelemetry.red_flag_triggered == True)
        )
    )

    reason = data.reason.strip()
    db.add(BreakGlassAccess(performed_by=admin.id, patient_user_id=patient.id, reason=reason))
    db.add(SecurityAuditTrail(
        performed_by=admin.id,
        action="BREAK_GLASS",
        target_resource=f"users:{patient.id}",
        ip_address=request.client.host if request.client else None
    ))

    return {
        "patient": {
            "name": profile.full_name,
            "phone": patient.phone_number,
            "study_id": study.study_id if study else None,
            "consent_status": profile.consent_status
        },
        "adherence_7d": {"taken": taken, "expected_slots": expected_slots},
        "red_flag_alerts": red_flags or 0,
        "reason_recorded": reason
    }


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
