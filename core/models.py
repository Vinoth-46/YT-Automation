from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import enum

Base = declarative_base()

class JobState(enum.Enum):
    SCHEDULED = "scheduled"
    GENERATING_SCRIPT = "generating_script"
    GENERATING_AUDIO = "generating_audio"
    GENERATING_VISUALS = "generating_visuals"
    RENDERING_DRAFT = "rendering_draft"
    AWAITING_APPROVAL = "awaiting_approval"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    FAILED = "failed"
    PAUSED = "paused"

class ContentType(enum.Enum):
    SHORT = "short"
    VIDEO = "video"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    timezone = Column(String, default="UTC")
    # 'manual' (wait for Telegram button) or 'auto' (post immediately)
    approval_mode = Column(String, default="auto")
    voice_profile = Column(String)
    
    schedules = relationship("Schedule", back_populates="user")
    channels = relationship("Channel", back_populates="user")

class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    channel_id = Column(String, unique=True)
    oauth_tokens = Column(JSON)
    default_category = Column(String)
    default_tags = Column(JSON)
    
    user = relationship("User", back_populates="channels")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    content_type = Column(SQLEnum(ContentType), default=ContentType.SHORT)
    recurrence = Column(String) # e.g., "daily"
    publish_time = Column(String) # e.g., "10:00"
    status = Column(String, default="active")
    
    user = relationship("User", back_populates="schedules")
    jobs = relationship("Job", back_populates="schedule")

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=True)
    planned_date = Column(DateTime)
    state = Column(SQLEnum(JobState), default=JobState.SCHEDULED)
    originality_score = Column(Float)
    voice_mode = Column(String)
    upload_mode = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    
    schedule = relationship("Schedule", back_populates="jobs")
    script = relationship("ScriptAsset", back_populates="job", uselist=False)
    audio = relationship("AudioAsset", back_populates="job", uselist=False)
    video = relationship("VideoAsset", back_populates="job", uselist=False)
    approvals = relationship("ApprovalAction", back_populates="job")

class ScriptAsset(Base):
    __tablename__ = "script_assets"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    topic = Column(String)
    script_text = Column(Text)
    hook_style = Column(String)
    similarity_score = Column(Float)
    title = Column(String)
    description = Column(Text)
    hashtags = Column(JSON)
    
    job = relationship("Job", back_populates="script")

class AudioAsset(Base):
    __tablename__ = "audio_assets"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    model_name = Column(String)
    quality_mode = Column(String)
    audio_path = Column(String)
    duration = Column(Float)
    
    job = relationship("Job", back_populates="audio")

class VideoAsset(Base):
    __tablename__ = "video_assets"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    draft_path = Column(String)
    final_path = Column(String)
    aspect_ratio = Column(String)
    visual_mode = Column(String)
    
    job = relationship("Job", back_populates="video")

class ApprovalAction(Base):
    __tablename__ = "approval_actions"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    action_type = Column(String) # e.g., "approve", "regenerate"
    actor = Column(String) # telegram_id
    timestamp = Column(DateTime, server_default=func.now())
    notes = Column(Text)
    
    job = relationship("Job", back_populates="approvals")
