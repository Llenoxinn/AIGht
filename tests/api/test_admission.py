from concurrent.futures import ThreadPoolExecutor

import pytest
from redis.exceptions import ConnectionError

from aight_api.store import identity
from conftest import import_text, session


def test_concurrent_replays_commit_once(environment):
    client, store = environment
    current, headers = session(client)
    expires = store.read(store.key(current["session_id"]))["expires_ms"]
    def replay(_):
        docid = identity("doc")
        document = {"id": docid, "session_id": current["session_id"], "input_type": "text", "status": "queued", "expires_ms": expires, "generation": "test"}
        return store.admit(current["session_id"], docid, "ingestion", {}, "synthetic-request-0001", "same-fingerprint", document)[0]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(replay, range(4)))
        assert results == [results[0]] * 4
    assert len(store.queue.get_job_ids()) == 1
    assert store.read(store.key(current["session_id"]))["outstanding"] == 1


def test_precommit_failure_leaves_no_reservations_or_job(environment, monkeypatch):
    client, store = environment
    current, _ = session(client)
    docid = identity("doc")
    expires = store.read(store.key(current["session_id"]))["expires_ms"]
    document = {"input_type": "text", "status": "queued", "expires_ms": expires, "generation": "test"}
    def fail(*args, **kwargs):
        raise ConnectionError("Synthetic pre-commit outage")
    monkeypatch.setattr(store.queue, "enqueue_many", fail)
    with pytest.raises(ConnectionError):
        store.admit(current["session_id"], docid, "ingestion", {}, "synthetic-outage-0001", "fingerprint", document)
    record = store.read(store.key(current["session_id"]))
    assert record["documents_created"] == record["outstanding"] == record["provider_tokens_reserved"] == 0
    assert not store.queue.get_job_ids()
    assert store.read(store.key(current["session_id"], f"doc:{docid}")) is None


def test_lost_ack_recovers_accepted_source_with_same_key(environment, monkeypatch):
    client, store = environment
    current, headers = session(client)
    admit = store.admit
    def lose_ack(*args, **kwargs):
        admit(*args, **kwargs)
        raise ConnectionError("Synthetic lost EXEC acknowledgement")
    monkeypatch.setattr(store, "admit", lose_ack)
    response = client.post("/api/v1/documents/text", headers={**headers, "Idempotency-Key": "synthetic-request-0001"},
                           json={"text": "GWA must not exceed 2.00.", "title": "Synthetic scholarship"})
    assert response.status_code == 503
    assert len(list(store.settings.data_dir.glob("ses_*/doc_*/source.txt"))) == 1
    monkeypatch.setattr(store, "admit", admit)
    recovered = import_text(client, headers)
    assert recovered["operation_id"] == store.queue.get_job_ids()[0]
    assert len(list(store.settings.data_dir.glob("ses_*/doc_*/source.txt"))) == 1


def test_capacity_and_provider_budget_fail_before_queueing(environment):
    client, store = environment
    current, headers = session(client)
    import_text(client, headers)
    import_text(client, headers, key="synthetic-request-0002")
    blocked = client.post("/api/v1/documents/text", headers={**headers, "Idempotency-Key": "synthetic-request-0003"}, json={"text": "Third document"})
    assert blocked.status_code == 429
    assert len(store.queue.get_job_ids()) == 2
    assert len(list(store.settings.data_dir.glob("ses_*/doc_*/source.txt"))) == 2
    other, other_headers = session(client)
    store.settings.session_provider_tokens = 1
    blocked = client.post("/api/v1/documents/text", headers={**other_headers, "Idempotency-Key": "synthetic-budget-0001"}, json={"text": "Budget fixture"})
    assert blocked.status_code == 429
    assert store.read(store.key(other["session_id"]))["outstanding"] == 0
