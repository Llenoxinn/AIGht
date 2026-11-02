"""Opt-in check against a dedicated local test Redis, also run by CI."""
import os

import pytest
from redis import Redis
from rq.job import Job

from aight_api.config import Settings
from aight_api.store import Store, identity


@pytest.mark.skipif(not os.environ.get("AIGHT_TEST_REDIS_URL"), reason="Dedicated real Redis not configured")
def test_real_redis_admission_json_job_and_guarded_publication(tmp_path):
    client = Redis.from_url(os.environ["AIGHT_TEST_REDIS_URL"])
    store = Store(client, Settings(_env_file=None, data_dir=tmp_path))
    created = store.create_session("synthetic-test")
    sid, docid = created["session_id"], identity("doc")
    parent = store.read(store.key(sid))
    document = {"id": docid, "session_id": sid, "input_type": "text", "generation": "synthetic",
                "status": "queued", "expires_ms": parent["expires_ms"]}
    accepted = None
    try:
        accepted, first = store.admit(sid, docid, "ingestion", {}, "synthetic-real-redis-0001", "same-input", document)
        assert first
        replay, first = store.admit(sid, identity("doc"), "ingestion", {}, "synthetic-real-redis-0001", "same-input", document)
        assert replay == accepted and not first
        job = Job.fetch(accepted["operation_id"], connection=client, serializer=store.queue.serializer)
        assert list(job.args) == [sid, accepted["operation_id"]]
        operation, _ = store.claim(sid, accepted["operation_id"])
        assert store.finish(sid, operation, result={"warnings": [], "coverage": {"partial_pages": []}})
        assert store.operation(sid, accepted["operation_id"])["result"]["warnings"] == []
        assert store.read(store.key(sid))["outstanding"] == 0
        assert not store.finish(sid, operation, result={"stale": True})
        store.revoke_document(sid, docid)
        assert not store.finish(sid, operation, result={"resurrected": True})
    finally:
        if accepted:
            Job.fetch(accepted["operation_id"], connection=client, serializer=store.queue.serializer).delete()
        for key in client.scan_iter(match=store.key(sid, "*")+"*"):
            client.delete(key)
        client.delete(f"aight:token:{parent['token_digest']}")
        client.srem("aight:cleanup", f"{sid}/{docid}")
