"""
PMAS — Pydantic Schemas (Data Contracts)
Request/response validation for all API endpoints.
"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Union
from datetime import date, datetime
from uuid import UUID


# ─── Auth Schemas ───────────────────────────────────────────

class UserRegister(BaseModel):
    """Self-registration is patient-only. Staff (pharmacist/admin) accounts
    are created by an administrator via the admin endpoints."""
    phone_number: str = Field(..., pattern=r"^(\+91\d{10}|\d{10})$")
    password: str = Field(..., min_length=8, max_length=100)
    preferred_language: str = Field(default="en", max_length=10)


class UserLogin(BaseModel):
    phone_number: str = Field(..., pattern=r"^(\+91\d{10}|\d{10})$")
    password: str = Field(...)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str


class EnrollmentResponse(BaseModel):
    """Enrollment result — includes the one-time ACTIVATION CODE the pharmacist
    relays to the patient. The patient activates the account on their own
    device and chooses their own password; the pharmacist never sets or sees
    the patient's password (PRD v1.1 §4A / G8)."""
    user_id: str
    role: str = "patient"
    study_id: str
    activation_code: str
    activation_expires_days: int = 7


class ActivationRequest(BaseModel):
    """Patient-side account activation for pharmacist-enrolled patients."""
    phone_number: str = Field(..., pattern=r"^\d{10}$")
    activation_code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=100)


class BreakGlassRequest(BaseModel):
    """Admin break-glass access request — a written reason is mandatory (G9)."""
    phone_number: str = Field(..., pattern=r"^\d{10}$")
    reason: str = Field(..., min_length=10, max_length=500)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)


# ─── Admin Schemas (account governance) ────────────────────

class AdminUserResponse(BaseModel):
    user_id: str
    phone_number: str
    role: str
    is_active: bool
    preferred_language: str
    created_at: Optional[datetime] = None


class AdminUserCreate(BaseModel):
    phone_number: str = Field(..., pattern=r"^(\+91\d{10}|\d{10})$")
    password: str = Field(..., min_length=8, max_length=100)
    role: str = Field(..., pattern=r"^(pharmacist|admin)$")
    preferred_language: str = Field(default="en", max_length=10)


class AdminUserUpdate(BaseModel):
    role: Optional[str] = Field(None, pattern=r"^(patient|pharmacist|admin)$")
    is_active: Optional[bool] = None


# ─── Profile Schemas ────────────────────────────────────────

class PatientProfileCreate(BaseModel):
    full_name: str = Field(..., max_length=100)
    hospital_mrn: Optional[str] = Field(None, max_length=50)
    emergency_contact_name: Optional[str] = Field(None, max_length=100)
    emergency_contact_phone: Optional[str] = Field(None, pattern=r"^(\+91\d{10}|\d{10})$")
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=20)
    blood_group: Optional[str] = Field(None, max_length=5)
    known_allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    consent_timestamp: datetime
    consent_version: str = "1.0"
    consent_checks: Optional[Union[dict, list]] = None  # app sends the three v2 acknowledgement states as an array
    consent_status: bool = False


class PatientProfileResponse(BaseModel):
    user_id: UUID
    full_name: str
    hospital_mrn: Optional[str]
    emergency_contact_name: Optional[str]
    emergency_contact_phone: Optional[str]
    date_of_birth: Optional[date]
    gender: Optional[str]
    blood_group: Optional[str]
    known_allergies: Optional[str]
    chronic_conditions: Optional[str]

    class Config:
        from_attributes = True


# ─── Medication Schemas ─────────────────────────────────────

class MedicationPlanCreate(BaseModel):
    medicine_name: str = Field(..., max_length=150)
    dosage: str = Field(..., max_length=50)
    frequency_morning: bool = False
    frequency_afternoon: bool = False
    frequency_night: bool = False
    morning_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    afternoon_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    night_time: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")
    start_date: date
    end_date: date
    instructions_localized: Optional[str] = None

    @model_validator(mode="after")
    def check_plan(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if not (self.frequency_morning or self.frequency_afternoon or self.frequency_night):
            raise ValueError("At least one dose slot (morning/afternoon/night) must be selected")
        return self


class MedicationPlanResponse(BaseModel):
    id: UUID
    medicine_name: str
    dosage: str
    frequency_morning: bool
    frequency_afternoon: bool
    frequency_night: bool
    morning_time: Optional[str]
    afternoon_time: Optional[str]
    night_time: Optional[str]
    start_date: date
    end_date: date
    instructions_localized: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


# ─── Adherence Schemas ──────────────────────────────────────

class AdherenceRecordCreate(BaseModel):
    medication_id: UUID
    dose_date: date
    dose_slot: str = Field(..., pattern=r"^(morning|afternoon|night)$")
    status: str = Field(..., pattern=r"^(taken|delayed|missed)$")


class AdherenceRecordResponse(BaseModel):
    id: UUID
    medication_id: UUID
    dose_date: date
    dose_slot: str
    status: str
    recorded_at: datetime

    class Config:
        from_attributes = True


class AdherenceSummary(BaseModel):
    total_scheduled: int
    total_taken: int
    adherence_pct: float


# ─── Symptom Schemas ────────────────────────────────────────

class SymptomLogCreate(BaseModel):
    log_date: date
    pain_score: int = Field(default=0, ge=0, le=10)
    systolic_bp: Optional[int] = Field(None, ge=50, le=260)
    diastolic_bp: Optional[int] = Field(None, ge=30, le=160)
    temperature: Optional[float] = Field(None, ge=35.0, le=42.0)
    weight_kg: Optional[float] = Field(None, ge=1.0, le=300.0)
    symptoms_observed: Optional[str] = None
    side_effects: Optional[str] = None
    additional_notes: Optional[str] = None


class SymptomLogResponse(BaseModel):
    id: UUID
    log_date: date
    pain_score: int
    systolic_bp: Optional[int]
    diastolic_bp: Optional[int]
    temperature: Optional[float]
    weight_kg: Optional[float]
    red_flag_triggered: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SymptomResponse(BaseModel):
    status: str
    red_flag_alert: bool
    action_required: Optional[str] = None


# ─── Appointment Schemas ────────────────────────────────────

class AppointmentCreate(BaseModel):
    appointment_date: date
    appointment_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    doctor_name: str = Field(..., max_length=150)
    department: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class AppointmentResponse(BaseModel):
    id: UUID
    appointment_date: date
    appointment_time: str
    doctor_name: str
    department: Optional[str]
    notes: Optional[str]
    status: str

    class Config:
        from_attributes = True


# ─── Pharmacist Dashboard Schemas ───────────────────────────

class PatientEnrollment(BaseModel):
    """Pharmacist registers a new patient"""
    phone_number: str = Field(..., pattern=r"^(\+91\d{10}|\d{10})$")
    full_name: str = Field(..., max_length=100)
    hospital_mrn: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    preferred_language: str = "en"
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    known_allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None


class PharmacistDashboard(BaseModel):
    total_patients: int
    active_medications: int
    today_adherence_avg: float
    red_flag_alerts: int
    recent_patients: List[dict]
