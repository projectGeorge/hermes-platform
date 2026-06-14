# Hermes - Multi-Agent Logistics Platform

Hermes is a web platform that automates freight forwarding workflows using AI agents. It transforms unstructured emails into structured orders, matches carriers intelligently, and provides real-time shipment monitoring.

## Features

- **Smart Ingestion**: Extract structured data from emails using local AI models
- **Carrier Matching**: Intelligent scoring of 58 carriers based on route, price, reliability, and ADR compliance
- **Real-time Monitoring**: Track shipments with automated alerts for delays and risks
- **Contextual Assistant**: AI-powered chat assistant with memory of past conversations
- **Human-in-the-Loop**: Operator review at critical decision points

## Tech Stack

**Frontend**
- React 19, TypeScript, Vite 7
- Tailwind CSS 4, TanStack Query, React Router 7
- Clerk authentication, Leaflet maps

**Backend**
- Python, FastAPI (async), SQLAlchemy 2.0
- LangGraph for agent orchestration
- PostgreSQL 15, ChromaDB (vector store)
- Alembic migrations

**AI/ML**
- Hybrid inference: Local SLM (LM Studio) + Cloud LLM (OpenRouter)
- RAG with ChromaDB for contextual memory
- Deterministic fallback parser when AI unavailable

## Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- Docker and Docker Compose
- Git

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd hermes
```

2. Start infrastructure services:
```bash
docker compose up -d
```

This starts PostgreSQL (port 5432) and ChromaDB (port 8001).

3. Configure backend environment:
```bash
cd app/backend
cp .env.example .env
```

Edit `.env` with your configuration. Minimum required:
```env
DATABASE_URL=postgresql://hermes_user:hermes_password@localhost:5432/hermes_db
CHROMA_HOST=http://localhost:8001

# Clerk authentication (get from clerk.com)
CLERK_SECRET_KEY=sk_test_...
CLERK_JWT_KEY=-----BEGIN PUBLIC KEY-----...
CLERK_AUTHORIZED_PARTIES=http://localhost:5173

# AI models (optional - system works without AI)
INGESTION_MODEL_PROVIDER=lm_studio
INGESTION_MODEL_NAME=qwen2.5:3b-instruct
REASONING_MODEL_PROVIDER=openrouter
REASONING_MODEL_NAME=deepseek/deepseek-chat
REASONING_MODEL_API_KEY=sk-or-...
```

4. Install backend dependencies and run migrations:
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
alembic upgrade head
```

5. Install frontend dependencies:
```bash
cd ../frontend
npm install
cp .env.example .env
```

Edit `app/frontend/.env`:
```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
```

## Running the Application

**Backend** (from `app/backend/`):
```bash
uvicorn app.backend.main:app --reload --port 8000
```

**Frontend** (from `app/frontend/`):
```bash
npm run dev
```

Open http://localhost:5173 in your browser.

## Optional: AI Model Setup

### Local AI (LM Studio)

1. Download and install [LM Studio](https://lmstudio.ai)
2. Download a 3B-4B model (Qwen2.5 3B, Phi-3.5 Mini, or Llama 3.2 3B)
3. Start the server on port 1234
4. Configure in `.env`:
```env
INGESTION_MODEL_PROVIDER=lm_studio
LM_STUDIO_BASE_URL=http://127.0.0.1:1234/v1
INGESTION_MODEL_NAME=<model-name>
```

### Cloud AI (OpenRouter)

1. Create account at [openrouter.ai](https://openrouter.ai)
2. Generate API key
3. Configure in `.env`:
```env
REASONING_MODEL_PROVIDER=openrouter
REASONING_MODEL_NAME=deepseek/deepseek-chat
REASONING_MODEL_API_KEY=sk-or-...
```

## Testing

**Backend tests:**
```bash
cd app/backend
python -m pytest tests/ -v
```

**Frontend tests:**
```bash
cd app/frontend
npm test
```

## Project Structure

```
hermes/
├── app/
│   ├── backend/          # Python FastAPI backend
│   │   ├── api/          # REST endpoints
│   │   ├── core/         # Configuration, enums
│   │   ├── db/           # Database session
│   │   ├── models/       # SQLAlchemy models (15 tables)
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # Business logic and agents
│   │   └── tests/        # Backend tests
│   └── frontend/         # React TypeScript frontend
│       ├── src/
│       │   ├── app/      # Routing, layout
│       │   ├── features/ # Feature modules
│       │   └── lib/      # Utilities
│       └── package.json
├── alembic/              # Database migrations
├── docker-compose.yml    # PostgreSQL + ChromaDB
── README.md
```

## Architecture

Hermes uses a multi-agent architecture with five specialized modules:

1. **Orchestrator**: Coordinates workflow and logs all state transitions
2. **Ingestion Agent**: Extracts structured data from emails using LangGraph
3. **Carrier Search Agent**: Scores carriers with multi-criteria algorithm
4. **Monitoring Agent**: Generates alerts based on deterministic rules
5. **Smart Comms**: Contextual assistant with RAG memory

All agents produce entries in an append-only activity log visible in the dashboard.

## License

MIT

---

Developed by Jorge Repullo for the Software Engineering Degree - University of Málaga (2026)
