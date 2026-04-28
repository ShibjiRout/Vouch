import redis
import rq
from rq import Queue
from app.config import REDIS_URL

_ssl_opts = {"ssl_cert_reqs": None} if REDIS_URL.startswith("rediss") else {}
connection = redis.from_url(REDIS_URL, **_ssl_opts)
queue = Queue(connection=connection)


def enqueue_job(func, *args, **kwargs):
    try:
        job = queue.enqueue(func, *args, **kwargs)
        return job.id
    except Exception as e:
        raise Exception(f"Failed to enqueue job: {e}")


def get_job_status(job_id: str) -> dict:
    try:
        job = queue.fetch_job(job_id)
        if job is None:
            return {"status": "not_found", "message": "No job with this ID"}

        status = job.get_status()

        if status == "finished":
            return {"status": "finished", "message": "PDF processing complete"}
        elif status == "failed":
            return {"status": "failed", "message": str(job.exc_info)}
        elif status == "started":
            return {"status": "processing", "message": "PDF is being processed"}
        else:
            return {"status": "queued", "message": "Waiting in line"}
    except Exception as e:
        raise Exception(f"Failed to get job status: {e}")


def is_processing(case_id: str) -> bool:
    try:
        jobs = queue.get_jobs()
        for job in jobs:
            if job.args and len(job.args) > 0 and job.args[0] == case_id:
                return True

        workers = rq.Worker.all(connection=connection)
        for worker in workers:
            current_job = worker.get_current_job()
            if current_job and current_job.args and current_job.args[0] == case_id:
                return True

        return False
    except Exception as e:
        raise Exception(f"Failed to check processing status: {e}")
