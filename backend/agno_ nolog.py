import asyncio
import json
import os
from pathlib import Path
import uuid
from fastapi import FastAPI, HTTPException,Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.mcp import MCPTools

from dotenv import load_dotenv
import tiktoken
from rich.pretty import pprint
from rich.console import Console
from requests_oauthlib import OAuth2Session
from google_auth_oauthlib.flow import Flow
from asyncio.subprocess import PIPE

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import jwt
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

load_dotenv()
JWT_SECRET = os.getenv("JWT_SECRET") or "your-secret-key-here"
console = Console()

# Initialize FastAPI security
security = HTTPBearer()

# Available OAuth scopes with descriptions
AVAILABLE_SCOPES = {
    'drive': {
        'scope': 'https://www.googleapis.com/auth/drive',
        'description': 'Full access to Google Drive files and folders'
    },
    'gmail_readonly': {
        'scope': 'https://www.googleapis.com/auth/gmail.readonly',
        'description': 'Read-only access to Gmail'
    },
    'gmail_full': {
        'scope': 'https://www.googleapis.com/auth/gmail.modify',
        'description': 'Full access to Gmail (read, send, modify)'
    },
    'gmail_labels': {
        'scope': 'https://www.googleapis.com/auth/gmail.labels',
        'description': 'Manage Gmail labels'
    },
    'gmail_compose': {
        'scope': 'https://www.googleapis.com/auth/gmail.compose',
        'description': 'Compose Gmail messages'
    },
    'calendar_events': {
        'scope': 'https://www.googleapis.com/auth/calendar.events',
        'description': 'Manage calendar events'
    },
    'calendar_readonly': {
        'scope': 'https://www.googleapis.com/auth/calendar.readonly',
        'description': 'Read-only access to calendar'
    },
    'documents': {
        'scope': 'https://www.googleapis.com/auth/documents',
        'description': 'Access Google Docs'
    },
    'spreadsheets': {
        'scope': 'https://www.googleapis.com/auth/spreadsheets',
        'description': 'Access Google Sheets'
    },
    'spreadsheets_readonly': {
        'scope': 'https://www.googleapis.com/auth/spreadsheets.readonly',
        'description': 'Read-only access to Google Sheets'
    }
}

# Initialize tokenizer for token counting
try:
    tokenizer = tiktoken.encoding_for_model("gpt-4")
except:
    tokenizer = tiktoken.get_encoding("cl100k_base")

# FastAPI app
app = FastAPI(title="MCP Chatbot API", version="1.0.0")

def generate_jwt(user: Dict[str, Any]) -> str:

    payload = {
        'id': user['id'],
        'email': user['email'],
        'name': user['name'],
        'picture': user['picture'],
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_jwt(token: str) -> Optional[Dict[str, Any]]:

    try:
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except jwt.InvalidTokenError:
        return None

# JWT Authentication dependency
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """
    Dependency to get current user from JWT token
    
    Args:
        credentials: HTTP Authorization credentials
    
    Returns:
        Decoded user data from JWT
    
    Raises:
        HTTPException: If token is invalid or expired
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization token required")
    
    token = credentials.credentials
    user_data = verify_jwt(token)
    
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return user_data

# Alternative dependency for endpoints that need user_id from token
async def get_user_id_from_token(current_user: Dict[str, Any] = Depends(get_current_user)) -> str:
    """
    Extract user ID from JWT token
    
    Args:
        current_user: Current user data from JWT
    
    Returns:
        User ID string
    """
    return str(current_user['id'])

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for user sessions (in production, use Redis or database)
user_sessions = {}
oauth_flows = {}

# Pydantic models
class ScopeSelection(BaseModel):
    scopes: List[str]

class ChatMessage(BaseModel):
    message: str
    stream: bool = True

class ChatResponse(BaseModel):
    response: str
    token_usage: Dict[str, int]
    timestamp: str

class AuthStatus(BaseModel):
    authenticated: bool
    scopes: List[str]
    email: Optional[str] = None
    
class UserStats(BaseModel):
    total_chats: int
    total_tokens: int
    session_created: Optional[str]
    last_activity: Optional[str]
    scopes: List[str]

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: Dict[str, Any]
    expires_in: int

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
async def run_agent_chat(message: str, user_id: str, use_streaming: bool = True) -> Dict[str, Any]:
    """Run the agent chat and return response."""
    if user_id not in user_sessions:
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    user_session = user_sessions[user_id]
    token_data = user_session['token_data']
    
    session_tokens = {
        "input_tokens": count_tokens(message),
        "output_tokens": 0,
        "total_tokens": 0
    }
    
    # Get originally requested scopes
    selected_scopes = user_session['selected_scopes']  
    selected_scope_urls = [AVAILABLE_SCOPES[s]['scope'] for s in selected_scopes if s in AVAILABLE_SCOPES]
    
    # Use the intersection of requested scopes and granted scopes
    granted_scopes = set(token_data['scopes'])
    requested_scopes = set(selected_scope_urls)
    
    # Only send scopes that were both requested and granted
    filtered_scopes = list(requested_scopes.intersection(granted_scopes))
    
    # Log the scope filtering for debugging
    console.print(f"[blue]User {user_id} - Requested: {len(requested_scopes)} scopes, Granted: {len(granted_scopes)} scopes, Using: {len(filtered_scopes)} scopes[/blue]")
    
    # Prepare environment variables for MCP server
    env_vars = {
        "GOOGLE_ACCESS_TOKEN": token_data['access_token'],
        "GOOGLE_REFRESH_TOKEN": token_data['refresh_token'],
        "GOOGLE_TOKEN_EXPIRES_AT": str(int(token_data['expires_at'] * 1000)),
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID"),
        "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET"),
        "SESSION_USER_ID": user_id,
        "GOOGLE_AUTHORIZED_SCOPES": json.dumps(filtered_scopes),
        "JWT_SECRET": JWT_SECRET  # Pass JWT secret to MCP toolkit
    }
    
    # ... rest of the function remains the same
    
    # Initialize variables for cleanup
    process = None
    stderr_task = None
    
    try:
        process = await asyncio.create_subprocess_exec(
            "python", "mcp_toolkit.py",
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
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
        
        async with stdio_client(StdioServerParameters(
            command="python",
            args=["mcp_toolkit.py"],
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
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")
        
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


# API Routes

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "MCP Chatbot API",
        "version": "1.0.0",
        "endpoints": {
            "auth": "/auth/scopes",
            "chat": "/chat",
            "status": "/auth/status",
            "login": "/auth/login"
        }
    }

@app.get("/auth/scopes")
async def get_available_scopes():
    """Get available OAuth scopes for selection."""
    return {
        "available_scopes": AVAILABLE_SCOPES,
        "description": "Select the scopes you want to authorize for Google services"
    }

@app.post("/auth/scopes")
async def select_scopes(scope_selection: ScopeSelection, request: Request):
    """Select scopes and initiate OAuth flow."""
    # Validate selected scopes
    invalid_scopes = [s for s in scope_selection.scopes if s not in AVAILABLE_SCOPES]
    if invalid_scopes:
        raise HTTPException(status_code=400, detail=f"Invalid scopes: {invalid_scopes}")
    
    # Generate user session ID
    user_id = str(uuid.uuid4())
    
    # Convert scope names to actual scope URLs
    selected_scope_urls = [AVAILABLE_SCOPES[s]['scope'] for s in scope_selection.scopes]
    
    # Create OAuth flow
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="OAuth credentials not configured")
    
    # Get base URL from request
    base_url = str(request.base_url).rstrip('/')
    redirect_uri = f"{base_url}/auth/callback"
    
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        },
        scopes=selected_scope_urls
    )
    flow.redirect_uri = redirect_uri
    
    # Generate authorization URL
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    # Store flow and user session
    oauth_flows[state] = {
        "flow": flow,
        "user_id": user_id,
        "selected_scopes": scope_selection.scopes
    }
    
    return {
        "auth_url": auth_url,
        "user_id": user_id,
        "state": state,
        "message": "Visit the auth_url to authorize the application"
    }
@app.get("/auth/callback")
async def oauth_callback(request: Request):
    """Handle OAuth callback and generate JWT token."""
    # Get authorization code and state from query params
    code = request.query_params.get('code')
    state = request.query_params.get('state')
    error = request.query_params.get('error')
    
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state")
    
    if state not in oauth_flows:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    
    oauth_data = oauth_flows[state]
    flow = oauth_data["flow"]
    user_id = oauth_data["user_id"]
    
    try:
        # Set environment variable to relax token scope validation
        os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
        
        # Get the originally requested scopes from oauth_data
        requested_scopes = [AVAILABLE_SCOPES[s]['scope'] for s in oauth_data["selected_scopes"]]
        
        # Alternative approach: Use requests_oauthlib directly to bypass strict validation
        from requests_oauthlib import OAuth2Session
        import requests
        
        # Create OAuth2 session with the requested scopes
        oauth2_session = OAuth2Session(
            client_id=flow.client_config['client_id'],
            redirect_uri=flow.redirect_uri,
            scope=requested_scopes
        )
        
        # Fetch token with relaxed validation
        token = oauth2_session.fetch_token(
            flow.client_config['token_uri'],
            code=code,
            client_secret=flow.client_config['client_secret'],
            include_granted_scopes=True
        )
        
        # Create credentials from the token
        from google.oauth2.credentials import Credentials
        
        # Handle scopes - they might be a string or a list
        token_scopes = token.get('scope', [])
        if isinstance(token_scopes, str):
            scopes_list = token_scopes.split()
        elif isinstance(token_scopes, list):
            scopes_list = token_scopes
        else:
            scopes_list = []
            
        credentials = Credentials(
            token=token['access_token'],
            refresh_token=token.get('refresh_token'),
            token_uri=flow.client_config['token_uri'],
            client_id=flow.client_config['client_id'],
            client_secret=flow.client_config['client_secret'],
            scopes=scopes_list
        )
        
        # Set expiry if available
        if 'expires_in' in token:

            credentials.expiry = datetime.utcnow() + timedelta(seconds=token['expires_in'])
        
        # Get user info from the token (if available)
        user_info = {}
        if 'https://www.googleapis.com/auth/userinfo.email' in credentials.scopes:
            try:
                # Get user info using the access token
                user_info_response = requests.get(
                    'https://www.googleapis.com/oauth2/v2/userinfo',
                    headers={'Authorization': f'Bearer {credentials.token}'}
                )
                if user_info_response.status_code == 200:
                    user_info = user_info_response.json()
            except Exception as e:
                console.print(f"[yellow]Could not fetch user info: {e}[/yellow]")
        
        # Check if we have at least the requested scopes
        granted_scopes = set(credentials.scopes or [])
        required_scopes = set(requested_scopes)
        
        console.print(f"[blue]Requested scopes: {required_scopes}[/blue]")
        console.print(f"[green]Granted scopes: {granted_scopes}[/green]")
        
        # Check if we have the essential scopes we requested
        if not required_scopes.issubset(granted_scopes):
            missing_scopes = required_scopes - granted_scopes
            console.print(f"[yellow]Warning: Some requested scopes not granted: {list(missing_scopes)}[/yellow]")
            # Continue anyway - we'll work with what we have
        
        # Create user data for JWT
        user_data = {
            "id": user_id,
            "email": user_info.get('email', ''),
            "name": user_info.get('name', 'User'),
            "picture": user_info.get('picture', '')
        }
        
        # Generate JWT token
        jwt_token = generate_jwt(user_data)
        
        # Store user session with all granted scopes
        user_sessions[user_id] = {
            "token_data": {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "expires_at": credentials.expiry.timestamp() if credentials.expiry else None,
                "scopes": list(granted_scopes)  # Store all granted scopes
            },
            "selected_scopes": oauth_data["selected_scopes"],  # Keep track of originally requested scopes
            "granted_scopes": list(granted_scopes),  # Store all granted scopes
            "authenticated": True,
            "created_at": datetime.utcnow().isoformat(),
            "user_data": user_data
        }
        
        # Clean up oauth flow
        del oauth_flows[state]
        
        return HTMLResponse(content=f"""
        <html>
            <head><title>Authorization Successful</title></head>
            <body>
                <h2>Authorization Successful!</h2>
                <p>You can now close this window and use the API.</p>
                <p><strong>Your JWT Token:</strong></p>
                <textarea readonly style="width: 100%; height: 100px; font-family: monospace;">{jwt_token}</textarea>
                <p><strong>Your User ID:</strong> {user_id}</p>
                <p><strong>User Email:</strong> {user_data.get('email', 'Not available')}</p>
                <p><strong>Requested Scopes:</strong> {', '.join(oauth_data["selected_scopes"])}</p>
                <p><strong>Total Granted Scopes:</strong> {len(granted_scopes)} scopes</p>
                <p><strong>Essential Scopes Status:</strong> {'✓ All requested scopes granted' if required_scopes.issubset(granted_scopes) else '⚠ Some requested scopes missing'}</p>
                <p>Use this JWT token in your API requests as Authorization: Bearer token</p>
            </body>
        </html>
        """)
        
    except Exception as e:
        console.print(f"[red]OAuth callback error: {e}[/red]")
        raise HTTPException(status_code=500, detail=f"OAuth callback error: {str(e)}")
    finally:
        # Clean up environment variable
        if 'OAUTHLIB_RELAX_TOKEN_SCOPE' in os.environ:
            del os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE']
@app.get("/auth/status")
async def get_auth_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Check authentication status for current user."""
    user_id = str(current_user['id'])
    
    if user_id not in user_sessions:
        return AuthStatus(authenticated=False, scopes=[])
    
    user_session = user_sessions[user_id]
    return {
        "authenticated": user_session["authenticated"],
        "requested_scopes": user_session["selected_scopes"],
        "granted_scopes": user_session.get("granted_scopes", []),
        "email": current_user.get("email"),
        "total_granted_scopes": len(user_session.get("granted_scopes", []))
    }
@app.post("/auth/login")
async def login_with_jwt(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Login endpoint that validates JWT and returns user info."""
    user_id = str(current_user['id'])
    
    if user_id not in user_sessions:
        raise HTTPException(status_code=401, detail="User session not found")
    
    # Generate new token (refresh)
    new_token = generate_jwt(current_user)
    
    return LoginResponse(
        access_token=new_token,
        token_type="bearer",
        user=current_user,
        expires_in=24 * 60 * 60  # 24 hours in seconds
    )

@app.post("/chat")
async def chat(
    chat_message: ChatMessage,
    user_id: str = Depends(get_user_id_from_token)
):
    """Send a message to the agent and get response."""
    if user_id not in user_sessions:
        raise HTTPException(status_code=401, detail="User not authenticated. Please complete OAuth flow first.")
    
    try:
        result = await run_agent_chat(
            message=chat_message.message,
            user_id=user_id,
            use_streaming=chat_message.stream
        )
        
        return ChatResponse(
            response=result["response"],
            token_usage=result["token_usage"],
            timestamp=result["timestamp"]
        )
        
    except Exception as e:
        console.print(f"[red]Chat error: {e}[/red]")
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

@app.delete("/auth/logout")
async def logout(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Logout current user and clear session."""
    user_id = str(current_user['id'])
    
    if user_id in user_sessions:
        del user_sessions[user_id]
        return {"message": "User logged out successfully"}
    else:
        raise HTTPException(status_code=404, detail="User session not found")

@app.get("/sessions")
async def get_active_sessions(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get information about active sessions (for debugging)."""
    # Only show current user's session for security
    user_id = str(current_user['id'])
    
    if user_id in user_sessions:
        session = user_sessions[user_id]
        return {
            "user_session": {
                "scopes": session["selected_scopes"],
                "authenticated": session["authenticated"],
                "created_at": session["created_at"],
                "user_data": session.get("user_data", {})
            }
        }
    else:
        return {"user_session": None}

@app.get("/me")
async def get_current_user_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get current user information from JWT."""
    return {
        "user": current_user,
        "message": "Current user information"
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    # Check required environment variables
    required_env_vars = ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "OPENAI_API_KEY", "JWT_SECRET"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        console.print(f"[red]Missing required environment variables: {missing_vars}[/red]")
        console.print("[yellow]Please set these in your .env file[/yellow]")
        exit(1)
    
    console.print("[bold green]Starting MCP Chatbot API Server...[/bold green]")
    console.print("[bold blue]Available endpoints:[/bold blue]")
    console.print("  - GET  /auth/scopes - Get available OAuth scopes")
    console.print("  - POST /auth/scopes - Select scopes and start OAuth")
    console.print("  - GET  /auth/status - Check authentication status (requires JWT)")
    console.print("  - POST /auth/login - Login with JWT token")
    console.print("  - POST /chat - Send message to agent (requires JWT)")
    console.print("  - DELETE /auth/logout - Logout user (requires JWT)")
    console.print("  - GET  /sessions - View user session (requires JWT)")
    console.print("  - GET  /me - Get current user info (requires JWT)")
    console.print("  - GET  /health - Health check")
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")