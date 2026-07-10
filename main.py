import os
import json
import sqlite3
import hashlib
import requests
from datetime import datetime, timezone

from sentence_transformers import SentenceTransformer, util
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# ----------------------------
# Config
# ----------------------------
JOB_EMBED_MODEL = "TechWolf/JobBERT-v2"
RERANK_MODEL = "Qwen/Qwen3-Reranker-8B"  # optional; can disable if too heavy
USE_RERANKER = True

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

DB_PATH = "job_tracker.db"
THRESHOLD = 0.72
TOP_K = 20

PROFILE_TEXT = """
Senior .NET / React engineer specializing in C#, .NET Core, ASP.NET Core, Entity Framework Core,
REST APIs, OData, React, Azure, Docker, Kubernetes, SQL Server, PostgreSQL, CI/CD, and financial systems.
"""

KEYWORDS = [".net", "c#", "react", "asp.net", "aspnet", "dotnet", "azure", "docker", "api", "backend"]

# ----------------------------
# Storage
# ----------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            job_id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            url TEXT,
            score REAL,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def job_id_from(job):
    raw = f"{job.get('title','')}_{job.get('company','')}_{job.get('url','')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def already_seen(job_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM seen_jobs WHERE job_id = ?", (job_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def save_job(job, score):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO seen_jobs (job_id, title, company, url, score, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        job_id_from(job),
        job.get("title"),
        job.get("company"),
        job.get("url"),
        float(score),
        datetime.now(timezone.utc).isoformat()
    ))
    conn.commit()
    conn.close()

# ----------------------------
# Telegram
# ----------------------------
def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables.")

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()

# ----------------------------
# Job source
# Replace this with your own scraper/API feed
# ----------------------------
def fetch_jobs():
    return [
        {
            "title": "Senior Backend Developer (.NET)",
            "company": "Example Bank",
            "location": "Nairobi",
            "description": "Build scalable REST APIs using .NET Core, SQL Server, Azure, Docker, and CI/CD.",
            "url": "https://example.com/job1"
        },
        {
            "title": "Full Stack Engineer",
            "company": "Tech Company",
            "location": "Remote",
            "description": "React frontend with backend services in C#/.NET, Azure, and PostgreSQL.",
            "url": "https://example.com/job2"
        }
    ]

# ----------------------------
# Filtering
# ----------------------------
def keyword_filter(job):
    text = " ".join([
        job.get("title", ""),
        job.get("company", ""),
        job.get("description", ""),
        job.get("location", "")
    ]).lower()
    return any(k in text for k in KEYWORDS)

# ----------------------------
# Scoring
# ----------------------------
embedder = SentenceTransformer(JOB_EMBED_MODEL)

if USE_RERANKER:
    rerank_tokenizer = AutoTokenizer.from_pretrained(RERANK_MODEL)
    rerank_model = AutoModelForSequenceClassification.from_pretrained(RERANK_MODEL)
    rerank_model.eval()
else:
    rerank_tokenizer = None
    rerank_model = None

profile_embedding = embedder.encode(PROFILE_TEXT, convert_to_tensor=True, normalize_embeddings=True)

def embed_score(job):
    text = f"{job.get('title','')}\n{job.get('description','')}\n{job.get('company','')}\n{job.get('location','')}"
    emb = embedder.encode(text, convert_to_tensor=True, normalize_embeddings=True)
    return float(util.cos_sim(profile_embedding, emb).item())

def rerank_score(job):
    if not USE_RERANKER:
        return None

    query = PROFILE_TEXT.strip()
    passage = f"{job.get('title','')}. {job.get('description','')}"

    inputs = rerank_tokenizer(query, passage, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = rerank_model(**inputs).logits

    if logits.shape[-1] == 1:
        score = torch.sigmoid(logits).item()
    else:
        score = torch.softmax(logits, dim=-1)[0, -1].item()
    return float(score)

def final_score(job):
    base = embed_score(job)
    if USE_RERANKER:
        rr = rerank_score(job)
        if rr is None:
            return base
        return 0.6 * base + 0.4 * rr
    return base

# ----------------------------
# Alert formatting
# ----------------------------
def format_alert(job, score):
    return (
        f"*New high-match job detected*\n\n"
        f"*Title:* {job.get('title')}\n"
        f"*Company:* {job.get('company')}\n"
        f"*Location:* {job.get('location')}\n"
        f"*Score:* {score:.3f}\n"
        f"*URL:* {job.get('url')}\n"
    )

# ----------------------------
# Main run
# ----------------------------
def run():
    init_db()
    jobs = fetch_jobs()

    scored = []
    for job in jobs:
        if not keyword_filter(job):
            continue
        score = final_score(job)
        scored.append((job, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_jobs = scored[:TOP_K]

    for job, score in top_jobs:
        jid = job_id_from(job)
        if already_seen(jid):
            continue
        if score >= THRESHOLD:
            message = format_alert(job, score)
            send_telegram_message(message)
            save_job(job, score)

if __name__ == "__main__":
    run()