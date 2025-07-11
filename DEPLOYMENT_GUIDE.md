# MCP Chatbot API v2.0 - Complete Deployment Guide

This guide provides step-by-step instructions for deploying the MCP Chatbot API both locally and on various cloud platforms.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Production Deployment](#production-deployment)
   - [Railway](#railway-deployment)
   - [Render](#render-deployment)
   - [DigitalOcean](#digitalocean-deployment)
   - [AWS](#aws-deployment)
   - [Google Cloud Platform](#google-cloud-platform)
4. [Environment Variables](#environment-variables)
5. [Troubleshooting](#troubleshooting)

## Prerequisites

Before starting, ensure you have:

- **Python 3.11+** installed
- **Docker** and **Docker Compose** installed
- **Git** installed
- **Google Cloud Console** account with OAuth2 credentials
- **OpenAI API** key
- **Supabase** account and database

### Required Google OAuth2 Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the following APIs:
   - Google Drive API
   - Gmail API
   - Google Calendar API
   - Google Docs API
4. Create OAuth2 credentials:
   - Go to "Credentials" → "Create Credentials" → "OAuth 2.0 Client IDs"
   - Application type: "Web application"
   - Add authorized redirect URIs:
     - `http://localhost:8000/auth/callback` (for local development)
     - `https://yourdomain.com/auth/callback` (for production)

### Supabase Database Setup

1. Create a [Supabase](https://supabase.com) account
2. Create a new project
3. Go to Settings → Database
4. Copy the connection string (it should look like: `postgresql://postgres:[password]@[host]:5432/postgres`)

---

## Local Development Setup

### Step 1: Clone and Setup Project

```bash
# Clone the repository
git clone <your-repo-url>
cd mcp-chatbot-api

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your credentials
nano .env  # or use your preferred editor
```

Fill in your `.env` file:

```env
# Database Configuration (Supabase PostgreSQL)
DATABASE_URL=postgresql+asyncpg://postgres:your_password@db.your_project.supabase.co:5432/postgres

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Google OAuth Configuration
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here

# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here

# JWT Configuration
JWT_SECRET=your_super_secret_jwt_key_here_make_it_long_and_random

# Optional: Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

### Step 3: Database Initialization

```bash
# Initialize database tables
python scripts/init_db.py
```

### Step 4: Start Services

#### Option A: Using Docker Compose (Recommended)

```bash
# Start all services (API, Redis, Worker, Flower)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

Services will be available at:
- **API Server**: http://localhost:8000
- **Flower (Celery Monitor)**: http://localhost:5555
- **Redis**: localhost:6379

#### Option B: Manual Setup

**Terminal 1 - Start Redis:**
```bash
# Install Redis (if not using Docker)
# On macOS: brew install redis
# On Ubuntu: sudo apt-get install redis-server
# On Windows: Use Docker or WSL

redis-server
```

**Terminal 2 - Start API Server:**
```bash
python scripts/run_api.py
```

**Terminal 3 - Start Celery Worker:**
```bash
python scripts/run_worker.py
```

**Terminal 4 - Start Flower (Optional):**
```bash
celery -A backend.celeryconfig flower --port=5555
```

### Step 5: Test the Setup

```bash
# Test API health
curl http://localhost:8000/health

# Test authentication flow
curl http://localhost:8000/auth/scopes
```

---

## Production Deployment

### Railway Deployment

Railway is excellent for quick deployments with automatic scaling.

#### Step 1: Prepare for Railway

1. Create a `railway.toml` file:

```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "uvicorn backend.backend:app --host 0.0.0.0 --port $PORT"

[[services]]
name = "api"

[[services]]
name = "worker"
startCommand = "celery -A backend.celeryconfig worker --loglevel=info --queues=mcp_queue,default --pool=prefork"

[[services]]
name = "flower"
startCommand = "celery -A backend.celeryconfig flower --port=$PORT"
```

2. Create a `Procfile`:

```
web: uvicorn backend.backend:app --host 0.0.0.0 --port $PORT
worker: celery -A backend.celeryconfig worker --loglevel=info --queues=mcp_queue,default --pool=prefork
flower: celery -A backend.celeryconfig flower --port=$PORT
```

#### Step 2: Deploy to Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Initialize project
railway init

# Add Redis addon
railway add redis

# Set environment variables
railway variables set DATABASE_URL="your_supabase_url"
railway variables set GOOGLE_CLIENT_ID="your_client_id"
railway variables set GOOGLE_CLIENT_SECRET="your_client_secret"
railway variables set OPENAI_API_KEY="your_openai_key"
railway variables set JWT_SECRET="your_jwt_secret"

# Deploy
railway up
```

### Render Deployment

Render provides excellent free tier options.

#### Step 1: Create render.yaml

```yaml
services:
  - type: web
    name: mcp-api
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn backend.backend:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: REDIS_URL
        fromService:
          type: redis
          name: mcp-redis
          property: connectionString
      - key: GOOGLE_CLIENT_ID
        sync: false
      - key: GOOGLE_CLIENT_SECRET
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: JWT_SECRET
        sync: false

  - type: worker
    name: mcp-worker
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "celery -A backend.celeryconfig worker --loglevel=info --queues=mcp_queue,default --pool=prefork"
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: REDIS_URL
        fromService:
          type: redis
          name: mcp-redis
          property: connectionString
      - key: GOOGLE_CLIENT_ID
        sync: false
      - key: GOOGLE_CLIENT_SECRET
        sync: false
      - key: OPENAI_API_KEY
        sync: false
      - key: JWT_SECRET
        sync: false

  - type: redis
    name: mcp-redis
    ipAllowList: []
```

#### Step 2: Deploy to Render

1. Connect your GitHub repository to Render
2. Create a new "Blueprint" deployment
3. Upload the `render.yaml` file
4. Set environment variables in Render dashboard
5. Deploy

### DigitalOcean App Platform

#### Step 1: Create .do/app.yaml

```yaml
name: mcp-chatbot-api
services:
- name: api
  source_dir: /
  github:
    repo: your-username/your-repo
    branch: main
  run_command: uvicorn backend.backend:app --host 0.0.0.0 --port $PORT
  environment_slug: python
  instance_count: 1
  instance_size_slug: basic-xxs
  envs:
  - key: DATABASE_URL
    scope: RUN_TIME
    type: SECRET
  - key: REDIS_URL
    scope: RUN_TIME
    type: SECRET
  - key: GOOGLE_CLIENT_ID
    scope: RUN_TIME
    type: SECRET
  - key: GOOGLE_CLIENT_SECRET
    scope: RUN_TIME
    type: SECRET
  - key: OPENAI_API_KEY
    scope: RUN_TIME
    type: SECRET
  - key: JWT_SECRET
    scope: RUN_TIME
    type: SECRET
  http_port: 8080

- name: worker
  source_dir: /
  github:
    repo: your-username/your-repo
    branch: main
  run_command: celery -A backend.celeryconfig worker --loglevel=info --queues=mcp_queue,default --pool=prefork
  environment_slug: python
  instance_count: 1
  instance_size_slug: basic-xxs
  envs:
  - key: DATABASE_URL
    scope: RUN_TIME
    type: SECRET
  - key: REDIS_URL
    scope: RUN_TIME
    type: SECRET
  - key: GOOGLE_CLIENT_ID
    scope: RUN_TIME
    type: SECRET
  - key: GOOGLE_CLIENT_SECRET
    scope: RUN_TIME
    type: SECRET
  - key: OPENAI_API_KEY
    scope: RUN_TIME
    type: SECRET
  - key: JWT_SECRET
    scope: RUN_TIME
    type: SECRET

databases:
- name: redis
  engine: REDIS
  version: "7"
```

#### Step 2: Deploy to DigitalOcean

```bash
# Install doctl CLI
# Follow instructions at: https://docs.digitalocean.com/reference/doctl/how-to/install/

# Authenticate
doctl auth init

# Create app
doctl apps create .do/app.yaml

# Update app (for subsequent deployments)
doctl apps update YOUR_APP_ID --spec .do/app.yaml
```

### AWS Deployment (ECS + Fargate)

#### Step 1: Create Dockerfile.prod

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Default command
CMD ["uvicorn", "backend.backend:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### Step 2: Create docker-compose.prod.yml

```yaml
version: '3.8'

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.prod
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      - redis

  worker:
    build:
      context: .
      dockerfile: Dockerfile.prod
    command: celery -A backend.celeryconfig worker --loglevel=info --queues=mcp_queue,default --pool=prefork
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

#### Step 3: Deploy to AWS ECS

1. **Push to ECR:**

```bash
# Create ECR repository
aws ecr create-repository --repository-name mcp-chatbot-api

# Get login token
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -f Dockerfile.prod -t mcp-chatbot-api .
docker tag mcp-chatbot-api:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/mcp-chatbot-api:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/mcp-chatbot-api:latest
```

2. **Create ECS Task Definition** (use AWS Console or CLI)
3. **Create ECS Service** with load balancer
4. **Set up ElastiCache Redis** cluster
5. **Configure environment variables** in ECS

### Google Cloud Platform (Cloud Run)

#### Step 1: Create cloudbuild.yaml

```yaml
steps:
  # Build the container image
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-f', 'Dockerfile.prod', '-t', 'gcr.io/$PROJECT_ID/mcp-chatbot-api', '.']
  
  # Push the container image to Container Registry
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/$PROJECT_ID/mcp-chatbot-api']
  
  # Deploy container image to Cloud Run
  - name: 'gcr.io/cloud-builders/gcloud'
    args:
    - 'run'
    - 'deploy'
    - 'mcp-chatbot-api'
    - '--image'
    - 'gcr.io/$PROJECT_ID/mcp-chatbot-api'
    - '--region'
    - 'us-central1'
    - '--platform'
    - 'managed'
    - '--allow-unauthenticated'

images:
- gcr.io/$PROJECT_ID/mcp-chatbot-api
```

#### Step 2: Deploy to GCP

```bash
# Set project
gcloud config set project YOUR_PROJECT_ID

# Enable APIs
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable redis.googleapis.com

# Create Redis instance
gcloud redis instances create mcp-redis --size=1 --region=us-central1

# Deploy
gcloud builds submit --config cloudbuild.yaml

# Set environment variables
gcloud run services update mcp-chatbot-api \
  --set-env-vars DATABASE_URL="your_supabase_url" \
  --set-env-vars GOOGLE_CLIENT_ID="your_client_id" \
  --set-env-vars GOOGLE_CLIENT_SECRET="your_client_secret" \
  --set-env-vars OPENAI_API_KEY="your_openai_key" \
  --set-env-vars JWT_SECRET="your_jwt_secret" \
  --region us-central1
```

---

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Supabase PostgreSQL connection string | `postgresql+asyncpg://postgres:pass@host:5432/postgres` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `GOOGLE_CLIENT_ID` | Google OAuth2 client ID | `123456789-abc.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth2 client secret | `GOCSPX-abcdefghijklmnop` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-abcdefghijklmnopqrstuvwxyz` |
| `JWT_SECRET` | Secret key for JWT tokens | `your-super-secret-key-here` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CELERY_BROKER_URL` | Celery broker URL | Same as `REDIS_URL` |
| `CELERY_RESULT_BACKEND` | Celery result backend | Same as `REDIS_URL` |

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Issues

**Error**: `sqlalchemy.exc.OperationalError: connection failed`

**Solutions**:
- Verify DATABASE_URL format: `postgresql+asyncpg://user:pass@host:port/db`
- Check Supabase database is running
- Verify network connectivity
- Check firewall settings

#### 2. Redis Connection Issues

**Error**: `redis.exceptions.ConnectionError`

**Solutions**:
- Ensure Redis is running: `redis-cli ping`
- Check REDIS_URL format: `redis://host:port/db`
- Verify Redis is accessible from your application

#### 3. Google OAuth Issues

**Error**: `OAuth callback error`

**Solutions**:
- Verify redirect URIs in Google Console match your domain
- Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are correct
- Ensure required Google APIs are enabled

#### 4. Celery Worker Issues

**Error**: `celery.exceptions.WorkerLostError`

**Solutions**:
- Check worker logs: `docker-compose logs worker`
- Verify Redis connection from worker
- Increase worker memory limits
- Check for Python import errors

#### 5. MCP Toolkit Issues

**Error**: `MCP toolkit failed with return code 1`

**Solutions**:
- Check if `backend/mcp_toolkit.py` exists and is executable
- Verify all required Python packages are installed
- Check environment variables are passed correctly
- Review worker logs for detailed error messages

### Performance Optimization

#### For High Traffic

1. **Scale Workers**:
```bash
# Docker Compose
docker-compose up --scale worker=3

# Kubernetes
kubectl scale deployment worker --replicas=3
```

2. **Redis Optimization**:
```bash
# Increase Redis memory
redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru
```

3. **Database Connection Pooling**:
```python
# In database.py, increase pool size
async_engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=300,
)
```

#### Monitoring

1. **Health Checks**:
```bash
# API health
curl https://your-domain.com/health

# Flower monitoring
curl https://your-flower-domain.com/api/workers
```

2. **Logs**:
```bash
# Docker logs
docker-compose logs -f api worker

# Production logs (varies by platform)
railway logs
render logs
kubectl logs -f deployment/api
```

### Security Considerations

1. **Environment Variables**: Never commit `.env` files
2. **JWT Secret**: Use a strong, random secret key
3. **Database**: Use SSL connections in production
4. **Redis**: Enable authentication in production
5. **HTTPS**: Always use HTTPS in production
6. **CORS**: Configure appropriate CORS origins

---

## Support

For issues and questions:

1. Check the [troubleshooting section](#troubleshooting)
2. Review application logs
3. Verify environment variables
4. Check service status (API, Redis, Workers)
5. Consult platform-specific documentation

---

**Happy Deploying! 🚀**