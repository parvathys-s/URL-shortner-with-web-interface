from datetime import datetime, timedelta
import os
import string
import secrets
from typing import Optional

from fastapi import FastAPI, Request, Depends, Form, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl, AnyHttpUrl, ValidationError
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, func
from sqlalchemy.orm import sessionmaker, declarative_base, Session
import qrcode
from io import BytesIO
import base64

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

app = FastAPI(title="TinyFox - URL Shortener", version="1.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------------- Models ----------------
class Link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(16), unique=True, index=True, nullable=False)
    long_url = Column(String(2048), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    clicks = Column(Integer, default=0, nullable=False)
    last_accessed = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    note = Column(String(200), nullable=True)

Base.metadata.create_all(bind=engine)

# ---------------- Utilities ----------------
ALPHABET = string.ascii_letters + string.digits

def gen_code(n: int = 6, db: Session = None) -> str:
    """Generate a unique short code."""
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(n))
        if db is None:
            return code
        if not db.query(Link).filter_by(code=code).first():
            return code

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def make_qr_png_data(url: str) -> str:
    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")

# ---------------- Pydantic Schemas ----------------
class ShortenRequest(BaseModel):
    url: AnyHttpUrl
    custom_code: Optional[str] = None
    expires_in_days: Optional[int] = None
    note: Optional[str] = None

class ShortenResponse(BaseModel):
    code: str
    short_url: HttpUrl
    long_url: AnyHttpUrl
    expires_at: Optional[datetime] = None

# ---------------- Routes (UI) ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    recent = (
        db.query(Link)
        .order_by(Link.created_at.desc())
        .limit(10)
        .all()
    )
    return templates.TemplateResponse("index.html", {"request": request, "recent": recent, "base_url": BASE_URL})

@app.post("/shorten", response_class=HTMLResponse)
def shorten_ui(
    request: Request,
    long_url: str = Form(...),
    custom_code: Optional[str] = Form(None),
    expires_in_days: Optional[int] = Form(None),
    note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    # Validate URL
    try:
        _ = AnyHttpUrl.validate(long_url)
    except Exception:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": "Please enter a valid URL (including http:// or https://).",
            "recent": db.query(Link).order_by(Link.created_at.desc()).limit(10).all(),
            "base_url": BASE_URL
        })

    # Handle custom code
    if custom_code:
        if not (1 <= len(custom_code) <= 16) or any(c not in ALPHABET + "-_" for c in custom_code):
            return templates.TemplateResponse("index.html", {
                "request": request,
                "error": "Custom code must be 1–16 chars (letters, numbers, - or _).",
                "recent": db.query(Link).order_by(Link.created_at.desc()).limit(10).all(),
                "base_url": BASE_URL
            })
        existing = db.query(Link).filter_by(code=custom_code).first()
        if existing:
            return templates.TemplateResponse("index.html", {
                "request": request,
                "error": "That custom code is already taken.",
                "recent": db.query(Link).order_by(Link.created_at.desc()).limit(10).all(),
                "base_url": BASE_URL
            })
        code = custom_code
    else:
        code = gen_code(7, db)

    expires_at = None
    if expires_in_days:
        try:
            d = int(expires_in_days)
            if d > 0:
                expires_at = datetime.utcnow() + timedelta(days=d)
        except ValueError:
            pass

    link = Link(code=code, long_url=long_url, expires_at=expires_at, note=note)
    db.add(link)
    db.commit()
    db.refresh(link)

    short_url = f"{BASE_URL}/{link.code}"
    qr_data = make_qr_png_data(short_url)

    return templates.TemplateResponse("created.html", {"request": request, "link": link, "short_url": short_url, "qr_data": qr_data, "base_url": BASE_URL})

@app.get("/stats/{code}", response_class=HTMLResponse)
def stats(code: str, request: Request, db: Session = Depends(get_db)):
    link = db.query(Link).filter_by(code=code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Short code not found")
    short_url = f"{BASE_URL}/{link.code}"
    qr_data = make_qr_png_data(short_url)
    return templates.TemplateResponse("stats.html", {"request": request, "link": link, "short_url": short_url, "qr_data": qr_data, "base_url": BASE_URL})

# ---------------- Routes (API) ----------------
@app.post("/api/shorten", response_model=ShortenResponse)
def api_shorten(payload: ShortenRequest, db: Session = Depends(get_db)):
    code = payload.custom_code or gen_code(7, db)
    if payload.custom_code and db.query(Link).filter_by(code=payload.custom_code).first():
        raise HTTPException(status_code=409, detail="Custom code already exists")
    expires_at = None
    if payload.expires_in_days and payload.expires_in_days > 0:
        expires_at = datetime.utcnow() + timedelta(days=payload.expires_in_days)
    link = Link(code=code, long_url=str(payload.url), expires_at=expires_at, note=payload.note)
    db.add(link)
    db.commit()
    db.refresh(link)
    return ShortenResponse(code=code, short_url=f"{BASE_URL}/{code}", long_url=str(payload.url), expires_at=expires_at)

@app.get("/api/info/{code}")
def api_info(code: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter_by(code=code).first()
    if not link:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "code": link.code,
        "long_url": link.long_url,
        "created_at": link.created_at,
        "clicks": link.clicks,
        "last_accessed": link.last_accessed,
        "expires_at": link.expires_at,
        "active": link.active,
        "note": link.note,
        "short_url": f"{BASE_URL}/{link.code}",
    }

# ---------------- Redirect ----------------
@app.get("/{code}")
def redirect(code: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter_by(code=code).first()
    if not link or not link.active:
        raise HTTPException(status_code=404, detail="Not found")
    if link.expires_at and datetime.utcnow() > link.expires_at:
        link.active = False
        db.commit()
        raise HTTPException(status_code=410, detail="Link expired")
    link.clicks += 1
    link.last_accessed = datetime.utcnow()
    db.commit()
    response = RedirectResponse(url=link.long_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)