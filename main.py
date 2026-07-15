from dotenv import load_dotenv

from services.ai_job_scorers.ai_job_scorer import final_score
from services.notifications.email.email import send_email_notification
from services.notifications.email.render_email_body import render_job_card
from services.repo.repository import already_seen, init_db, save_job
from services.search_engine.search_engine import fetch_jobs
from services.string_handlers.string_handler import THRESHOLD, TOP_K, job_id_from, keyword_filter

load_dotenv() 

def run():
    init_db()

    while True:
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
            if already_seen(jid):
                continue
            if score >= THRESHOLD:
                # message = format_alert(job, score)
                # send_telegram_message(message)
                job_cards += render_job_card(job)
                save_job(job, score)

        if len(job_cards) != 0:
            send_email_notification(job_cards)


if __name__ == "__main__":
    run()