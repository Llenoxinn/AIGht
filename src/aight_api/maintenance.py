"""Run separately so cleanup still progresses while the worker is busy."""
import shutil
import time
from datetime import datetime

from redis import Redis
from rq.job import Job
from rq.exceptions import NoSuchJobError

from .config import settings
from .jobs import source_directory
from .models import ServiceError
from .store import Store, now_ms


def sweep(store: Store) -> dict:
    removed, failed = 0, 0
    root = store.settings.data_dir.resolve()
    if root.exists():
        for candidate in root.glob("ses_*/doc_*"):
            try:
                sid, docid = candidate.parent.name, candidate.name
                directory = source_directory(root, sid, docid)
                if not directory.is_dir():
                    continue
                live = store.read(store.key(sid))
                document = store.read(store.key(sid, f"doc:{docid}"))
                expired = not live or live["expires_ms"] <= now_ms()
                revoked = not live or not document or document["status"] == "deleted"
                # Allow an uncommitted upload time to finish; deletion/expiry has no grace period.
                staged = document is None and now_ms() - directory.stat().st_mtime * 1000 < 60_000 and live and not expired
                if (expired or revoked) and not staged:
                    for identifier in store.redis.smembers(store.key(sid, f"doc:{docid}:ops")):
                        jobid = identifier.decode() if isinstance(identifier, bytes) else identifier
                        try:
                            Job.fetch(jobid, connection=store.redis, serializer=store.queue.serializer).delete()
                        except NoSuchJobError:
                            pass
                    keys = list(store.redis.scan_iter(match=store.key(sid, f"doc:{docid}") + "*"))
                    for key in keys:
                        store.redis.delete(key)
                    for key in list(store.redis.scan_iter(match=store.key(sid, "op:*"))):
                        record = store.read(key)
                        if record and record["document_id"] == docid:
                            store.redis.delete(key)
                    shutil.rmtree(directory)
                    store.redis.srem("aight:cleanup", f"{sid}/{docid}")
                    removed += 1
            except (OSError, ValueError, KeyError, ServiceError):
                failed += 1
    # A crashed worker can leave a candidate after the file sweep. Reconcile Redis
    # independently of manifests, including late writes after a deletion sweep.
    for key in store.redis.scan_iter(match="aight:ses_*:doc:*"):
        decoded = key.decode() if isinstance(key, bytes) else key
        parts = decoded.split(":")
        sid, docid = parts[1], parts[3]
        parent = store.read(store.key(sid))
        document = store.read(store.key(sid, f"doc:{docid}"))
        if not parent or parent["expires_ms"] <= now_ms() or not document or document["status"] == "deleted":
            store.redis.delete(key)
    for key in store.redis.scan_iter(match="rq:job:op_*"):
        decoded = key.decode() if isinstance(key, bytes) else key
        if len(decoded.split(":")) != 3:
            continue
        try:
            job = Job.fetch(decoded.removeprefix("rq:job:"), connection=store.redis, serializer=store.queue.serializer)
            sid, opid = job.args
            store.operation(sid, opid)
        except NoSuchJobError:
            continue
        except ServiceError:
            job.delete()
    for key in store.redis.scan_iter(match="aight:ses_*:op:*"):
        operation = store.read(key)
        if operation:
            try:
                store.document(operation["session_id"], operation["document_id"])
            except ServiceError:
                store.redis.delete(key)
    # Markers contain identifiers only; the independent scans also cover expiry.
    store.redis.delete("aight:cleanup")
    for key in list(store.redis.scan_iter(match="aight:ses_*:op:*")):
        operation = store.read(key)
        if not operation or operation["state"] not in {"queued", "running"}:
            continue
        age = now_ms() - int(datetime.fromisoformat(operation["updated_at"].replace("Z", "+00:00")).timestamp() * 1000)
        deadline = store.settings.queue_timeout if operation["state"] == "queued" else store.settings.operation_timeout + 30
        if age < deadline * 1000:
            continue
        sid = operation["session_id"]
        if operation["state"] == "queued":
            claimed = store.claim(sid, operation["id"])
            if not claimed:
                continue
            operation, _ = claimed
        problem = ServiceError("processing_timeout", "This operation stopped or exceeded its waiting limit. Retry explicitly.", 503, True)
        update = {"status": "failed", "error": problem.safe()} if operation["kind"] == "ingestion" else None
        store.finish(sid, operation, error=problem.safe(), document=update)
    return {"removed_documents": removed, "cleanup_errors": failed}


if __name__ == "__main__":
    store = Store(Redis.from_url(settings.redis_url), settings)
    while True:
        try:
            result = sweep(store)
            if result["cleanup_errors"]:
                print("AIGht cleanup encountered storage errors; retry scheduled.", flush=True)
        except Exception:
            print("AIGht cleanup dependency unavailable; retry scheduled.", flush=True)
        time.sleep(15)
