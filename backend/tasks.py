import asyncio
import json
import os
import subprocess
import tempfile
from datetime import datetime
from typing import Dict, Any

from celery import current_task
from sqlalchemy.orm import Session

from .celeryconfig import celery_app
from .database import get_sync_db, SyncSessionLocal
from .models import JobRecord
import tiktoken
from dotenv import load_dotenv
load_dotenv()
# Initialize tokenizer for token counting
try:
    tokenizer = tiktoken.encoding_for_model("gpt-4")
except:
    tokenizer = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken."""
    if not text:
        return 0
    return len(tokenizer.encode(str(text)))

@celery_app.task(bind=True)
def run_mcp_toolkit(self, job_id: str, user_id: str, message: str, env_vars: Dict[str, Any]):
    """
    Celery task to run mcp_toolkit.py with user's environment variables
    
    Args:
        job_id: Database job record ID
        user_id: User ID from JWT
        message: User's input message
        env_vars: Environment variables for the MCP toolkit
    """
    db = SyncSessionLocal()
    
    try:
        # Update job status to running
        job = db.query(JobRecord).filter(JobRecord.id == job_id).first()
        if not job:
            raise Exception(f"Job {job_id} not found")
        
        job.status = "running"
        job.updated_at = datetime.utcnow()
        db.commit()
        
        # Count input tokens
        input_tokens = count_tokens(message)
        
        # Prepare environment for subprocess
        process_env = os.environ.copy()
        process_env.update(env_vars)
        
        try:
            # Run mcp_toolkit.py as subprocess
            result = subprocess.run(
                ["python", "backend/mcp_toolkit.py"],
                input=message,
                capture_output=True,
                text=True,
                env=process_env,
                timeout=1500,  # 25 minutes timeout
                cwd=os.getcwd()
            )
            
            if result.returncode != 0:
                error_msg = f"MCP toolkit failed with return code {result.returncode}\nSTDERR: {result.stderr}\nSTDOUT: {result.stdout}"
                raise Exception(error_msg)
            
            response_content = result.stdout.strip()
            
            if not response_content:
                response_content = "No output received from MCP toolkit"
            
            # Count output tokens
            output_tokens = count_tokens(response_content)
            total_tokens = input_tokens + output_tokens
            
            token_usage = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens
            }
            
            # Update job with success
            job.status = "completed"
            job.result = response_content
            job.token_usage = token_usage
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.commit()
            
            return {
                "status": "completed",
                "result": response_content,
                "token_usage": token_usage
            }
            
        except subprocess.TimeoutExpired:
            raise Exception("MCP toolkit execution timed out after 25 minutes")
        except subprocess.CalledProcessError as e:
            raise Exception(f"MCP toolkit process failed: {e}")
                
    except Exception as e:
        # Update job with failure
        error_message = str(e)
        job.status = "failed"
        job.error_message = error_message
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        db.commit()
        
        # Re-raise the exception so Celery marks the task as failed
        raise
        
    finally:
        db.close()

@celery_app.task
def cleanup_old_jobs():
    """Periodic task to clean up old job records"""
    db = SyncSessionLocal()
    try:
        # Delete jobs older than 7 days
        from datetime import timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=7)
        
        deleted_count = db.query(JobRecord).filter(
            JobRecord.created_at < cutoff_date
        ).delete()
        
        db.commit()
        return f"Cleaned up {deleted_count} old job records"
        
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()