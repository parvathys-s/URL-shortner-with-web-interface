# TinyFox — URL Shortener

A clean, production-ready URL shortener with a web UI, REST API, SQLite storage, QR codes, and Docker.

## Features
- Shorten long URLs with random or custom codes
- Auto-redirect `/{code}` → original URL
- Click tracking: total clicks + last accessed time
- Optional expiry in N days
- Notes per link
- Stats page + QR code for each short link
- REST API: `/api/shorten`, `/api/info/{code}`
- SQLite by default; swap `DATABASE_URL` for Postgres/MySQL
- Dockerfile + docker-compose for one-command start

## Quickstart (no Docker)
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export BASE_URL=http://127.0.0.1:8000
uvicorn main:app --reload
```
Open http://127.0.0.1:8000

## Quickstart with Docker
```bash
docker build -t tinyfox .
docker run -p 8000:8000 -e BASE_URL=http://127.0.0.1:8000 tinyfox
```
Or with compose (persists db to `./data.db`):
```bash
docker-compose up --build
```

## API
Create a short link:
```bash
curl -X POST http://127.0.0.1:8000/api/shorten \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","custom_code":"hello","expires_in_days":7,"note":"demo"}'
```
Fetch info:
```bash
curl http://127.0.0.1:8000/api/info/hello
```

## Config
- `BASE_URL`: the public base (e.g., `https://your-domain.com`)
- `DATABASE_URL`: SQLAlchemy URL. For Postgres:
  - `postgresql+psycopg2://user:pass@host:5432/dbname`

## Deploy
- Any platform that runs Docker (Render, Railway, Fly.io, etc.)
- Set `BASE_URL` to your public URL
- Mount a volume for the DB if you want persistence
```yaml
# Example Docker run on a server:
docker run -d --restart unless-stopped \
  -e BASE_URL=https://tiny.yourdomain.com \
  -e DATABASE_URL=sqlite:///./data.db \
  -v $(pwd)/data.db:/app/data.db \
  -p 8000:8000 tinyfox
```

## Notes
- This is a minimal but solid base; add auth/rate-limits/custom domains if needed.
- For Nginx ingress, proxy `/{code}` to the app so redirects work at root.