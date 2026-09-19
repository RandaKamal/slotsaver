# Relay — AI Recovery Engine for Service Businesses

See [FOLDER_STRUCTURE.md](FOLDER_STRUCTURE.md) for the repo layout and ownership map, and
[TEAM_INSTRUCTIONS.md](TEAM_INSTRUCTIONS.md) for role-by-role implementation guidance.

## Stack

- Frontend: Next.js, TypeScript, Tailwind CSS (`apps/web`)
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, SQLite (`apps/api`)
- AI: Gemini API (world understanding), NVIDIA Nemotron API (recovery planning)
- Voice: ElevenLabs
- Deployment: DigitalOcean (planned)

## Getting started

```bash
cp .env.example .env

# backend
cd apps/api
pip install -r requirements.txt
uvicorn app.main:app --reload

# frontend
cd apps/web
npm install
npm run dev
```