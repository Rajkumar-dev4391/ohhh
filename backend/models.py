from sqlalchemy import Column, String, Text, DateTime, Integer, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
import uuid
from dotenv import load_dotenv
load_dotenv()
Base = declarative_base()

class JobRecord(Base):
    __tablename__ = "job_records"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    message = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending, running, completed, failed
    result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    token_usage = Column(JSON, nullable=True)
    env_vars = Column(JSON, nullable=True)  # Store user's environment variables
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    def to_dict(self):
        return {
            "job_id": self.id,
            "user_id": self.user_id,
            "message": self.message,
            "status": self.status,
            "result": self.result,
            "error_message": self.error_message,
            "token_usage": self.token_usage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

class UserSession(Base):
    __tablename__ = "user_sessions"
    
    user_id = Column(String, primary_key=True)
    token_data = Column(JSON, nullable=False)
    selected_scopes = Column(JSON, nullable=False)
    granted_scopes = Column(JSON, nullable=False)
    authenticated = Column(Boolean, default=True)
    user_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        return {
            "user_id": self.user_id,
            "token_data": self.token_data,
            "selected_scopes": self.selected_scopes,
            "granted_scopes": self.granted_scopes,
            "authenticated": self.authenticated,
            "user_data": self.user_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }