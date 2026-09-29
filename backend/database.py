"""
PMAS — Database Configuration & Models
Dual-Vault architecture with SQLAlchemy ORM.
Vault A: Identity (PII) | Vault B: Clinical & Telemetry (HEOR)
"""
import os
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    create_engine, Column, String, Boolean, Integer, Float, Text,
    DateTime, Date, Time, ForeignKey, Enum as SAEnum, JSON, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from typing import AsyncGenerator

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/pmas")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# ─── Enums ──────────────────────────────────────────────────
import enum
class UserRole(enum.Enum):
    patient = "patient"
    pharmacist = "pharmacist"
    admin = "admin"

class DoseStatus(enum.Enum):
    taken = "taken"
    delayed = "delayed"
    missed = "missed"


# ─── VAULT A: IDENTITY (PII) ────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    phone_number = Column(String(15), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.patient, nullable=False)
    preferred_language = Column(String(10), default="en")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    profile = relationship("PatientProfile", back_populates="user", uselist=False, foreign_keys="PatientProfile.user_id")
    medications = relationship("MedicationPlan", back_populates="patient", foreign_keys="MedicationPlan.patient_id")


class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    hospital_mrn = Column(String(50))
    full_name = Column(String(100), nullable=False)
    emergency_contact_name = Column(String(100))
    emergency_contact_phone = Column(String(15))
    date_of_birth = Column(Date)
    gender = Column(String(20))
    blood_group = Column(String(5))
    known_allergies = Column(Text)
    chronic_conditions = Column(Text)
    # G10: NULL until the patient attests consent on their own device (§4A);
    # set once, at attestation time, by the patient app's sync. Never a placeholder.
    consent_timestamp = Column(DateTime(timezone=True), nullable=True)
    consent_version = Column(String(20), nullable=False)
    consent_checks = Column(JSONB)
    consent_status = Column(Boolean, default=True)
    # The pharmacist who enrolled this patient (NULL for self-registered
    # patients and legacy rows enrolled before this column existed)
    enrolled_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # foreign_keys is required now that two FKs point at users.id
    user = relationship("User", back_populates="profile", foreign_keys=[user_id])


# ─── VAULT B: CLINICAL & TELEMETRY ──────────────────────────

class MedicationPlan(Base):
    __tablename__ = "medication_plans"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    prescribed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    medicine_name = Column(String(150), nullable=False)
    dosage = Column(String(50), nullable=False)
    frequency_morning = Column(Boolean, default=False)
    frequency_afternoon = Column(Boolean, default=False)
    frequency_night = Column(Boolean, default=False)
    morning_time = Column(Time)
    afternoon_time = Column(Time)
    night_time = Column(Time)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    instructions_localized = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    patient = relationship("User", back_populates="medications", foreign_keys=[patient_id])
    adherence_records = relationship("AdherenceRecord", back_populates="medication")


class AdherenceRecord(Base):
    __tablename__ = "adherence_records"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    medication_id = Column(UUID(as_uuid=True), ForeignKey("medication_plans.id", ondelete="CASCADE"))
    dose_date = Column(Date, nullable=False)
    dose_slot = Column(String(10), nullable=False)
    status = Column(SAEnum(DoseStatus), nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("patient_id", "medication_id", "dose_date", "dose_slot"),)

    medication = relationship("MedicationPlan", back_populates="adherence_records")


class SymptomTelemetry(Base):
    __tablename__ = "symptom_telemetry"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    log_date = Column(Date, nullable=False)
    pain_score = Column(Integer)
    systolic_bp = Column(Integer)
    diastolic_bp = Column(Integer)
    temperature = Column(Float)
    weight_kg = Column(Float)
    symptoms_observed = Column(Text)
    side_effects = Column(Text)
    additional_notes = Column(Text)
    red_flag_triggered = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    appointment_date = Column(Date, nullable=False)
    appointment_time = Column(Time, nullable=False)
    doctor_name = Column(String(150), nullable=False)
    department = Column(String(100))
    notes = Column(Text)
    status = Column(String(20), default="scheduled")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SecurityAuditTrail(Base):
    __tablename__ = "security_audit_trail"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    performed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    action = Column(String(100), nullable=False)
    target_resource = Column(String(100), nullable=False)
    ip_address = Column(String(45))
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PendingActivation(Base):
    """One-time activation code for pharmacist-enrolled patients.

    The pharmacist never sets or sees the patient's password: enrollment
    leaves the account inactive with a hashed activation code; the patient
    activates it on their own device and chooses their own password (G8)."""
    __tablename__ = "pending_activations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    code_hash = Column(String(128), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class BreakGlassAccess(Base):
    """Exceptional admin access to a patient's clinical data (G9).

    Routine clinical access is pharmacist-only; an admin reaching patient data
    must state a reason, which is persisted here and in the audit trail."""
    __tablename__ = "break_glass_access"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    performed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    patient_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class StudyMetadata(Base):
    __tablename__ = "study_metadata"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    study_id = Column(String(20), unique=True, nullable=False)
    baseline_date = Column(Date)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ─── Database session dependency ────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
