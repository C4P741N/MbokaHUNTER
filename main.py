import os
import json
import sqlite3
import hashlib
import requests
from datetime import datetime, timezone, timedelta

import math
from dateutil import parser as dateparser


from sentence_transformers import SentenceTransformer, util
from transformers import AutoTokenizer, AutoModelForSequenceClassification

import torch
import re

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

from dotenv import load_dotenv
load_dotenv() 
# ----------------------------
# Config
# ----------------------------
JOB_EMBED_MODEL = "TechWolf/JobBERT-v2"
RERANK_MODEL = "Qwen/Qwen3-Reranker-8B"  # optional; can disable if too heavy
USE_RERANKER = False

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")          # <-- NEW: AI‑powered search
# Recency boosting
ENABLE_RECENCY_BOOST = True
MAX_RECENCY_BOOST = 1.5            # maximum multiplier for very recent jobs
RECENCY_HALF_LIFE_HOURS = 24       # hours until boost halves to ~1.0

DB_PATH = "job_tracker.db"
THRESHOLD = 0.1
TOP_K = 20

# Mail server configuration (replace with your actual info)
SMTP_SERVER = "smtp.gmail.com"  # Your SMTP server address
SMTP_PORT = 465  # Port number

# Sender information
SENDER_EMAIL = "bot.mboka@gmail.com"
SENDER_PASSWORD = "skfi lchk relb mdsx"

# Recipient information
RECEIVER_EMAIL = "m.kituku@hotmail.com"

PROFILE_TEXT = """
Senior .NET / React engineer specializing in C#, .NET Core, ASP.NET Core, Entity Framework Core,
REST APIs, OData, React, Azure, Docker, Kubernetes, SQL Server, PostgreSQL, CI/CD, and financial systems.
I am only interested in fully remote positions or jobs located in Kenya.
"""

KEYWORDS = [".net", "c#", "react", "asp.net", "aspnet", "dotnet", "azure", "docker", "api", "backend"]

# ----------------------------
# Storage (unchanged)
# ----------------------------
# def execute_query(sql_query):
#    execute_all(sql_query, True)

# def execute_crud(sql_query):
#     execute_all(sql_query, False)

# def execute_all(sql_query, is_select):
#     sqliteConnection = None
#     try:
#         sqliteConnection = sqlite3.connect(DB_PATH)
#         cur = sqliteConnection.cursor()
#         cur.execute(sql_query)
#         if not is_select:
#             sqliteConnection.commit()
#         else:
#             row = cur.fetchone()
#         sqliteConnection.close()
#         if(is_select):
#             return row is not None
#     except sqlite3.Error as error:
#         print("Exception occured -", error)
#     finally:
#         if sqliteConnection:
#             sqliteConnection.close()

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
# Telegram (unchanged)
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
# AI‑powered job source (NEW, replaces static list)
# ----------------------------
def build_search_query():
    """
    Build a Google‑friendly search query from your profile & keywords.
    This tells the AI search engine exactly what you're looking for.
    """
    # Use the most important technologies as required terms
    must_include = ' AND '.join(f'"{kw}"' for kw in ['.net', 'c#', 'react'])
    optional_include = ' OR '.join(KEYWORDS)  # just in case
    return f'({must_include}) ({optional_include}) (engineer OR developer)'

def fetch_jobs_from_serpapi():
    """
    Use SerpAPI's google_jobs engine to get structured job listings.
    (SerpAPI uses machine learning to extract the fields.)
    """
    if not SERPAPI_API_KEY:
        print("WARNING: SERPAPI_API_KEY not set. Returning empty job list.")
        return []

    query = build_search_query()
    print(f"Searching for jobs with query: {query}")

    params = {
        "engine": "google_jobs",
        "q": query,
        "api_key": SERPAPI_API_KEY,
        "hl": "en",
    }

    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"SerpAPI request failed: {e}")
        return []

    jobs = []
    for result in data.get("jobs_results", []):
        title = result.get("title", "")
        company = result.get("company_name", "")
        location = result.get("location", "")
        url = result.get("source_link") or result.get("share_link", "")

          # Attempt to grab a raw posting date
        posted_raw = None
        detected = result.get("detected_extensions", {})
        for key in ("posted", "date", "schedule", "posted_at", "posted_date", "posted_at"):
            if key in detected:
                posted_raw = detected[key]
                break
        if not posted_raw:
            posted_raw = result.get("posted") or result.get("date")
        
        description_parts = []

        for det in result.get("detected_extensions", {}).values():
            if isinstance(det, str):
                description_parts.append(det)
        description = " ".join(description_parts) if description_parts else ""

        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "url": url,
            "posted_raw": posted_raw

        })

    print(f"Found {len(jobs)} jobs via SerpAPI.")
    return jobs

def fetch_jobs():
    """Main entry point – returns a list of job dicts."""
    return fetch_jobs_from_serpapi()

# ----------------------------
# Filtering (unchanged)
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
# Scoring (unchanged)
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

def location_sentence(job):
    """Create a natural‑language description of the job's location and onsite requirements."""
    loc = job.get("location", "Unknown location")
    desc = job.get("description", "")
    # Simple hybrid detection – adjust keywords as needed
    is_hybrid = any(w in f"{job.get('title','')} {desc}".lower() 
                    for w in ["hybrid", "on-site", "onsite", "in-office", "partially remote"])
    arrangement = "hybrid/onsite" if is_hybrid else "remote"
    return f"This job is {arrangement} and located in {loc}."

def embed_score(job):
    text = (
        f"{job.get('title','')}\n"
        f"{job.get('description','')}\n"
        f"{job.get('company','')}\n"
        f"{location_sentence(job)}"
        )
    
    emb = embedder.encode(text, convert_to_tensor=True, normalize_embeddings=True)

    #Performs the comparison between the skills i have(currently stored in the vector profile_embedding) and the job that has been found stored in (encoded into a vector then stored in emb)
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

def get_recency_boost(job):
    if not ENABLE_RECENCY_BOOST:
        return 1.0

    date_str = job.get("posted_raw")
    if not date_str:
        return 1.0                # unknown age → no boost

    try:
        post_date = None
        #matches if has number and if contains day ago or days ago
        pattern = r'\d+\s+days?\s+ago'

        if re.search(pattern, date_str):
            today = datetime.now(timezone.utc)
            prev_days = date_str.split(' ')[0]
            previous_date = today - timedelta(days=int(prev_days))
            post_date = previous_date
        else:
            post_date = dateparser.parse(date_str)
        
        now = datetime.now(timezone.utc)
        # Make post_date timezone-aware if it isn't
        if post_date.tzinfo is None:
            post_date = post_date.replace(tzinfo=timezone.utc)
        delta = now - post_date
        hours = max(0, delta.total_seconds() / 3600)

        # Exponential decay: boost starts at MAX_RECENCY_BOOST and fades to 1.0
        boost = 1.0 + (MAX_RECENCY_BOOST - 1.0) * math.exp(-hours / RECENCY_HALF_LIFE_HOURS)
        return boost
    except Exception:
        return 1.0   # if parsing fails, no boost

def final_score(job):
    base = embed_score(job)
    if USE_RERANKER:
        rr = rerank_score(job)
        if rr is None:
            return base
        return 0.6 * base + 0.4 * rr
    
    # Multiply by recency boost – recent jobs get a higher final score
    recency = get_recency_boost(job)

    return base * recency

# ----------------------------
# Alert formatting (unchanged)
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
# Build html job posting
# ----------------------------
def assemble_job_card(job):
      return f"""
    <div style="border:1px solid #ddd; border-radius:8px; padding:16px; margin-bottom:20px;">
        <h2 style="margin:0; color:#2c3e50;">{job.get('title')}</h2>
        <p style="margin:6px 0;">
            <strong>{job.get('company')}</strong><br>
            📍 {job.get('location')}
        </p>

        <p>{job.get('description')}</p>

        <a href="{job.get('url')}"
           style="
               display:inline-block;
               padding:10px 18px;
               background:#007BFF;
               color:white;
               text-decoration:none;
               border-radius:5px;
           ">
            Apply Now
        </a>
    </div>
    """

def assemble_email(job_cards):
    return f"""
    <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background-color: #f5f5f5;
                    padding: 20px;
                }}

                .container {{
                    max-width: 700px;
                    margin: auto;
                    background: white;
                    padding: 30px;
                    border-radius: 10px;
                }}

                h1 {{
                    color: #333;
                }}

                p {{
                    color: #555;
                    line-height: 1.6;
                }}
            </style>
        </head>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background-color: #f5f5f5;
                    padding: 20px;
                }}

                .container {{
                    max-width: 700px;
                    margin: auto;
                    background: white;
                    padding: 30px;
                    border-radius: 10px;
                }}

                h1 {{
                    color: #333;
                }}

                p {{
                    color: #555;
                    line-height: 1.6;
                }}
            </style>
        </head>

        <body>

            <div class="container">

            <h1>Latest Job Opportunities</h1>

            <p>We found the following jobs that may interest you.</p>

            {job_cards}

            <hr>

            <p style="font-size:12px;color:#888;">
            You're receiving this email because you subscribed to job alerts.
            </p>

            </div>

        </body>
    </html>
"""

def send_email_notification(job_cards):

    server = None
    try:
        html_content = assemble_email(job_cards)

        # Create email object
        msg = MIMEMultipart()
        msg['From'] = Header("Mboka Bot", 'utf-8')  # Sender display name
        msg['To'] = Header("Krunch Sensei", 'utf-8') # Recipient display name
        msg['Subject'] = Header("Job Alerts", 'utf-8') # Email subject

        msg.attach(MIMEText(html_content, 'html', 'utf-8'))

        # # Create SMTP object and connect to the server
        # server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        # server.starttls() # Enable TLS encryption (usually required for port 587)

        # # Log in to the mailbox
        # server.login(SENDER_EMAIL, PASSWORD)

        # # Send the email
        # server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                server.connect()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())

        print("Email sent successfully!")

    except Exception as e:
            print(f"Failed to send email: {e}")
    finally:
        server.quit() # Close the connection




# ----------------------------
# Main run (unchanged)
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

    job_cards = ""

    for job, score in top_jobs:
        jid = job_id_from(job)
        # if already_seen(jid):
        #     continue
        if score >= THRESHOLD:
            # message = format_alert(job, score)
            # send_telegram_message(message)
            job_cards += assemble_job_card(job)
            save_job(job, score)

    if len(job_cards) != 0:
        send_email_notification(job_cards)


if __name__ == "__main__":
    run()