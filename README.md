# MCP Chatbot API v2.0 - Scalable Backend

A scalable FastAPI backend with Celery task processing and Supabase PostgreSQL integration for the MCP (Model Context Protocol) Chatbot system.

## Architecture Overview

- **FastAPI**: Web API framework with async support
- **Celery**: Distributed task queue for processing MCP toolkit operations
- **Redis**: Message broker for Celery and caching
- **Supabase PostgreSQL**: Database for job records and user sessions
- **JWT Authentication**: Secure user authentication with Google OAuth
- **Docker**: Containerized deployment

## Features

- ✅ **Scalable Task Processing**: Offload MCP toolkit execution to Celery workers
- ✅ **Database Persistence**: Store job records and user sessions in Supabase
- ✅ **JWT Authentication**: Preserved existing authentication logic
- ✅ **Async API**: FastAPI with async/await support
- ✅ **Docker Support**: Complete containerized setup
- ✅ **Health Monitoring**: Flower for Celery monitoring

## Quick Start

### 1. Environment Setup

Copy the example environment file and configure:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
DATABASE_URL=postgresql+asyncpg://username:password@host:port/database
REDIS_URL=redis://localhost:6379/0
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
OPENAI_API_KEY=your_openai_api_key
JWT_SECRET=your_jwt_secret_key_here
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Initialize Database

```bash
python scripts/init_db.py
```

### 4. Run with Docker Compose (Recommended)

```bash
docker-compose up -d
```

This starts:
- API server on http://localhost:8000
- Redis on localhost:6379
- Celery worker
- Flower monitoring on http://localhost:5555

### 5. Run Manually (Development)

Start Redis:
```bash
redis-server
```

Start the API server:
```bash
python scripts/run_api.py
```

Start Celery worker:
```bash
python scripts/run_worker.py
```

## API Endpoints

### Authentication (Preserved from v1)
- `GET /auth/scopes` - Get available OAuth scopes
- `POST /auth/scopes` - Select scopes and start OAuth flow
- `GET /auth/callback` - OAuth callback handler
- `GET /auth/status` - Check authentication status
- `POST /auth/login` - Login with JWT token
- `DELETE /auth/logout` - Logout user

### New Task Processing Endpoints
- `POST /run` - Queue a new MCP toolkit task
- `GET /result/{job_id}` - Get job result by ID
- `GET /jobs` - List user's jobs

### Utility Endpoints
- `GET /` - API information
- `GET /me` - Current user info
- `GET /health` - Health check

## Usage Example

### 1. Authenticate (same as v1)

```bash
# Get available scopes
curl http://localhost:8000/auth/scopes

# Select scopes and get OAuth URL
curl -X POST http://localhost:8000/auth/scopes \
  -H "Content-Type: application/json" \
  -d '{"scopes": ["drive", "gmail_full"]}'

# Visit the returned auth_url and complete OAuth flow
# You'll receive a JWT token
```

### 2. Queue a Task

```bash
curl -X POST http://localhost:8000/run \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "List my recent emails"}'
```

Response:
```json
{
  "job_id": "uuid-here",
  "status": "queued",
  "message": "Task has been queued for processing"
}
```

### 3. Check Result

```bash
curl http://localhost:8000/result/uuid-here \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Response:
```json
{
  "job_id": "uuid-here",
  "user_id": "user-uuid",
  "message": "List my recent emails",
  "status": "completed",
  "result": "Email listing results...",
  "token_usage": {
    "input_tokens": 10,
    "output_tokens": 150,
    "total_tokens": 160
  },
  "created_at": "2024-01-15T10:00:00Z",
  "completed_at": "2024-01-15T10:00:30Z"
}
```

## Database Schema

### JobRecord Table
- `id`: Primary key (UUID)
- `user_id`: User identifier from JWT
- `message`: User's input message
- `status`: pending, running, completed, failed
- `result`: Task output (when completed)
- `error_message`: Error details (when failed)
- `token_usage`: Token consumption metrics
- `env_vars`: User's environment variables
- `created_at`, `updated_at`, `completed_at`: Timestamps

### UserSession Table
- `user_id`: Primary key (from JWT)
- `token_data`: OAuth token information
- `selected_scopes`: Originally requested scopes
- `granted_scopes`: Actually granted scopes
- `authenticated`: Authentication status
- `user_data`: User profile information
- `created_at`, `updated_at`: Timestamps

## Scaling Considerations

### Horizontal Scaling
- Add more Celery workers: `docker-compose up --scale worker=3`
- Use Redis Cluster for high availability
- Use connection pooling for database

### Monitoring
- Flower dashboard: http://localhost:5555
- Health check endpoint: http://localhost:8000/health
- Database metrics via Supabase dashboard

### Security
- JWT tokens expire after 24 hours
- Environment variables for sensitive data
- User sessions isolated by user_id
- OAuth scopes properly filtered

## Migration from v1

The new API is backward compatible for authentication. Key changes:

1. **Replace `/chat` endpoint** with `/run` + `/result/{job_id}`
2. **User sessions** now stored in database instead of memory
3. **Task processing** is asynchronous via Celery
4. **Job history** is persisted and queryable

## Development

### Database Migrations

```bash
# Generate migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head
```

### Testing

```bash
# Run tests (add your test framework)
pytest tests/

# Test Celery task directly
python -c "from backend.tasks import run_mcp_toolkit; print(run_mcp_toolkit.delay('test', 'user', 'message', {}))"
```

## Production Deployment

1. **Use environment-specific configurations**
2. **Set up proper logging and monitoring**
3. **Use Redis Cluster or managed Redis**
4. **Configure proper database connection pooling**
5. **Set up load balancing for API servers**
6. **Use container orchestration (Kubernetes, etc.)**

## Troubleshooting

### Common Issues

1. **Database connection errors**: Check DATABASE_URL format
2. **Redis connection errors**: Ensure Redis is running
3. **Celery tasks stuck**: Check worker logs and restart workers
4. **OAuth errors**: Verify Google OAuth credentials

### Logs

```bash
# API logs
docker-compose logs api

# Worker logs
docker-compose logs worker

# Redis logs
docker-compose logs redis
```

## Support

For issues and questions:
1. Check the logs for error details
2. Verify environment variables are set correctly
3. Ensure all services are running (API, Redis, Workers)
4. Check Flower dashboard for task status