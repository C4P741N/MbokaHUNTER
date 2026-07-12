# Mboka-Ai, the automated job tracker

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-integrated-2496ED?logo=docker)](https://www.docker.com/)
[![Hugging Face](https://img.shields.io/badge/🤗-Transformers-FFD21E)](https://huggingface.co/)

An automated, containerized job aggregation and recommendation system that continuously monitors job boards, performs semantic relevance scoring using transformer-based embeddings, and delivers notifications for positions that closely match a predefined candidate profile.

The application is designed around a modular architecture, making it straightforward to extend with additional job sources, ranking models, notification providers, and storage backends.

---

## Architecture

```
                    +--------------------+
                    |   Job Sources      |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    |  Job Collectors    |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    | Data Normalization |
                    +---------+----------+
                              |
                              v
                    +--------------------+
                    | Semantic Scoring   |
                    | (JobBERT / SBERT)  |
                    +---------+----------+
                              |
               +--------------+--------------+
               |                             |
               v                             v
      +----------------+            +----------------+
      | SQLite Storage |            | Notifications  |
      | Deduplication  |            | Telegram/Email |
      +----------------+            +----------------+
```

---

# Features

- Automated job discovery from multiple sources.
- Semantic job matching using transformer embeddings.
- Configurable similarity thresholds.
- Intelligent relevance ranking.
- Duplicate detection using SQLite.
- Telegram and Email notification support.
- Docker-based deployment.
- Persistent Hugging Face model caching.
- Modular service-oriented architecture for easy extensibility.

---

# Semantic Matching Pipeline

Instead of relying solely on keyword matching, the tracker performs semantic similarity search.

1. Generate an embedding for the candidate profile.
2. Generate embeddings for newly discovered job postings.
3. Compute cosine similarity between profile and job embeddings.
4. Rank jobs by semantic relevance.
5. Persist unseen jobs.
6. Dispatch notifications for jobs exceeding the configured similarity threshold.

This approach allows the system to identify conceptually similar roles even when different terminology is used (e.g. *Software Engineer* vs *Backend Developer*).

---

# Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| ML Framework | PyTorch |
| Embeddings | Sentence Transformers |
| Embedding Model | JobBERT-v2 |
| Vector Similarity | Cosine Similarity |
| Storage | SQLite |
| Containerization | Docker |
| Notifications | Telegram Bot API / SMTP |
| Configuration | python-dotenv |
| Progress Reporting | tqdm |

---

# Installation

Clone the repository.

```bash
git clone https://github.com/your-username/automated-job-tracker.git

cd automated-job-tracker
```

Create a virtual environment.

```bash
python -m venv .venv
```

Activate the environment.

Linux/macOS

```bash
source .venv/bin/activate
```

Windows

```powershell
.venv\Scripts\activate
```

Install dependencies.

```bash
pip install -r requirements.txt
```

---

# Configuration

Create a `.env` file.

```env
TELEGRAM_BOT_TOKEN=<telegram_bot_token>
TELEGRAM_CHAT_ID=<telegram_chat_id>

SMTP_HOST=
SMTP_PORT=
SMTP_USERNAME=
SMTP_PASSWORD=

SIMILARITY_THRESHOLD=0.80
TOP_K_RESULTS=20
```

---

# Running

Execute locally.

```bash
python job_tracker.py
```

---

# Docker

Build and start the application.

```bash
./run.sh
```

---

# Hugging Face Model Cache

The Docker configuration mounts the local Hugging Face cache directory into the container.

This provides several advantages:

- prevents repeated model downloads
- significantly reduces startup time
- lowers bandwidth consumption
- allows offline execution after the initial download

---

# Data Storage

SQLite is used as the persistence layer for:

- processed jobs
- duplicate detection
- notification history
- application state

This guarantees that previously processed jobs are not repeatedly scored or notified.

---

# Scoring

Job relevance is determined using transformer embeddings.

```
Candidate Profile
        │
        ▼
Embedding Vector
        │
        │
        ├─────────────── Cosine Similarity ───────────────┐
        │                                                 │
        ▼                                                 ▼
 Job Embedding 1                                    Job Embedding N
        │                                                 │
        └──────────────────── Ranking ────────────────────┘
                            │
                            ▼
                  High Relevance Matches
```

The semantic search approach is substantially more robust than traditional keyword-based filtering and captures contextual similarity between job descriptions and candidate profiles.

---

# Development

The application supports remote debugging using `debugpy`.

Typical workflow:

1. Launch the application inside Docker.
2. Expose the debug port.
3. Attach Visual Studio Code.
4. Debug the application without rebuilding the container.

---

# Performance

Current optimizations include:

- batched embedding generation
- model caching
- duplicate detection
- configurable similarity threshold
- incremental processing of unseen jobs
- lightweight SQLite persistence

---

# Future Roadmap

- Multiple job providers
- Hybrid keyword + semantic search
- Resume parsing
- Automatic profile generation
- Vector database integration (FAISS/Qdrant/Pinecone)
- LLM-assisted job summarization
- Web-based administration dashboard
- Distributed worker architecture
- Historical analytics and reporting

---

# License

MIT License.
