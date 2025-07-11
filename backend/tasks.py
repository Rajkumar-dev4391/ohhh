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

# Import agno and MCP components
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.mcp import MCPTools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from rich.console import Console

load_dotenv()
console = Console()

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

async def create_agent(session, user_id: str):
    """Create an agent with MCP tools."""
    mcp_tools = MCPTools(session=session)
    await mcp_tools.initialize()
    
    return Agent(
        model=OpenAIChat(id="gpt-4o"),
        tools=[mcp_tools],
        markdown=True,
        show_tool_calls=True,
    )

async def run_agent_chat(message: str, user_id: str, env_vars: Dict[str, Any]) -> Dict[str, Any]:
    """Run the agent chat and return response."""
    
    session_tokens = {
        "input_tokens": count_tokens(message),
        "output_tokens": 0,
        "total_tokens": 0
    }
    
    # Initialize variables for cleanup
    process = None
    stderr_task = None
    
    try:
        # Create subprocess for MCP toolkit
        process = await asyncio.create_subprocess_exec(
            "python", "backend/mcp_toolkit.py",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **env_vars}
        )
        
        if process.returncode is not None:
            raise RuntimeError("MCP process failed to start")
            
        async def read_stderr():
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                console.print(f"[yellow]MCP stderr:[/yellow] {line.decode().strip()}")
                
        stderr_task = asyncio.create_task(read_stderr())
        
        # Use stdio_client to communicate with MCP toolkit
        async with stdio_client(StdioServerParameters(
            command="python",
            args=["backend/mcp_toolkit.py"],
            env=env_vars
        )) as (read, write):
            async with ClientSession(read, write) as session:
                agent = await create_agent(session, user_id)

                response = await agent.arun(message=message, markdown=True)
                response_content = str(response.content) if hasattr(response, 'content') else str(response)
                
                # Count tokens
                session_tokens["output_tokens"] = count_tokens(response_content)
                session_tokens["total_tokens"] = session_tokens["input_tokens"] + session_tokens["output_tokens"]
                
                return {
                    "response": response_content,
                    "token_usage": session_tokens,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
    except Exception as e:
        console.print(f"[red]Error in agent chat: {e}[/red]")
        raise Exception(f"Agent error: {str(e)}")
        
    finally:
        # Clean up stderr task
        if stderr_task:
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass
        
        # Clean up process
        if process and process.returncode is None:
            process.terminate()
            await process.wait()

@celery_app.task(bind=True)
def run_mcp_toolkit(self, job_id: str, user_id: str, message: str, env_vars: Dict[str, Any]):
    """
    Celery task to run agno agent with MCP toolkit
    
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
        
        # Run the agent chat in async context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                run_agent_chat(message, user_id, env_vars)
            )
            
            # Update job with success
            job.status = "completed"
            job.result = result["response"]
            job.token_usage = result["token_usage"]
            job.completed_at = datetime.utcnow()
            job.updated_at = datetime.utcnow()
            db.commit()
            
            return {
                "status": "completed",
                "result": result["response"],
                "token_usage": result["token_usage"]
            }
            
        finally:
            loop.close()
                
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