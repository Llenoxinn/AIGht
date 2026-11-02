import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from uuid import uuid4

from redis import Redis, WatchError
from rq import Queue
from rq.serializers import JSONSerializer

from .config import Settings
from .models import ServiceError


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat().replace("+00:00", "Z")


def packed(value: dict | list) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def identity(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


FINALIZE = """
local sraw=redis.call('GET',KEYS[1]); local draw=redis.call('GET',KEYS[2]); local oraw=redis.call('GET',KEYS[3])
if not sraw or not draw or not oraw then return 0 end
local s=cjson.decode(sraw); local d=cjson.decode(draw); local o=cjson.decode(oraw)
local clock=redis.call('TIME'); local now=tonumber(clock[1])*1000+math.floor(tonumber(clock[2])/1000)
if s.expires_ms<=now or d.expires_ms<=now or d.status=='deleted' or d.session_id~=s.id then return 0 end
if d.generation~=ARGV[1] or o.document_generation~=ARGV[1] or o.attempt_token~=ARGV[2] or o.state~='running' then return 0 end
if ARGV[4]~='' then
  redis.call('SET',KEYS[2],ARGV[4],'PXAT',d.expires_ms)
end
s.outstanding=math.max(0,s.outstanding-1)
redis.call('SET',KEYS[1],cjson.encode(s),'PXAT',s.expires_ms)
redis.call('SET',KEYS[3],ARGV[3],'PXAT',o.expires_ms)
return 1
"""


REVOKE = """
local draw=redis.call('GET',KEYS[1]); if not draw then return 0 end
local d=cjson.decode(draw); if d.session_id~=ARGV[1] or d.status=='deleted' then return 0 end
d.status='deleted'; d.generation=ARGV[2]; d.content_key=cjson.null
redis.call('SET',KEYS[1],cjson.encode(d),'PXAT',d.expires_ms)
local sraw=redis.call('GET',KEYS[2]); local s=sraw and cjson.decode(sraw) or nil
for _,id in ipairs(redis.call('SMEMBERS',KEYS[3])) do
  local key=ARGV[3]..id; local raw=redis.call('GET',key)
  if raw then
    local o=cjson.decode(raw)
    if o.state=='queued' or o.state=='running' then
      o.state='cancelled'; o.stage='cancelled'; o.result=cjson.null; o.error=cjson.null
      if s and not o.capacity_released then s.outstanding=math.max(0,s.outstanding-1) end
      o.capacity_released=true
      redis.call('SET',key,cjson.encode(o),'PXAT',o.expires_ms)
    end
  end
end
if s then redis.call('SET',KEYS[2],cjson.encode(s),'PXAT',s.expires_ms) end
return 1
"""


class Store:
    def __init__(self, client: Redis, settings: Settings):
        self.redis, self.settings = client, settings
        self.queue = Queue("aight", connection=client, serializer=JSONSerializer)

    @staticmethod
    def key(sid: str, suffix: str = "session") -> str:
        return f"aight:{sid}:{suffix}"

    def read(self, key: str) -> dict | None:
        raw = self.redis.get(key)
        return json.loads(raw) if raw else None

    def create_session(self, notice: str) -> dict:
        token, sid, created = secrets.token_urlsafe(32), identity("ses"), now_ms()
        digest = hashlib.sha256(token.encode()).hexdigest()
        expires = created + self.settings.session_seconds * 1000
        record = {"id": sid, "token_digest": digest, "created_at": iso(created),
                  "expires_at": iso(expires), "expires_ms": expires, "documents_created": 0,
                  "outstanding": 0, "provider_tokens_reserved": 0, "processing_notice_version": notice}
        with self.redis.pipeline(transaction=True) as pipe:
            pipe.set(self.key(sid), packed(record), pxat=expires)
            pipe.set(f"aight:token:{digest}", sid, pxat=expires)
            pipe.execute()
        return {"session_id": sid, "session_token": token, "created_at": iso(created),
                "expires_at": iso(expires), "processing_notice_version": notice}

    def authenticate(self, token: str) -> dict:
        digest = hashlib.sha256(token.encode()).hexdigest()
        raw = self.redis.get(f"aight:token:{digest}")
        sid = raw.decode() if isinstance(raw, bytes) else raw
        session = self.read(self.key(sid)) if sid else None
        if not session or session["expires_ms"] <= now_ms():
            raise ServiceError("invalid_session", "Start a new temporary session.", 401)
        return session

    def document(self, sid: str, docid: str, ready: bool = False) -> dict:
        session = self.read(self.key(sid))
        document = self.read(self.key(sid, f"doc:{docid}"))
        if not session or session["expires_ms"] <= now_ms() or not document or document["session_id"] != sid or document["status"] == "deleted" or document["expires_ms"] <= now_ms():
            raise ServiceError("not_found", "This resource is unavailable.", 404)
        if ready and document["status"] != "ready":
            raise ServiceError("document_not_ready", "This document is not ready.", 409, True)
        return document

    def operation(self, sid: str, opid: str) -> dict:
        operation = self.read(self.key(sid, f"op:{opid}"))
        if not operation or operation["session_id"] != sid:
            raise ServiceError("not_found", "This resource is unavailable.", 404)
        self.document(sid, operation["document_id"])
        return operation

    def admit(self, sid: str, docid: str, kind: str, payload: dict, idem: str,
              fingerprint: str, document: dict | None = None) -> tuple[dict, bool]:
        skey, dkey = self.key(sid), self.key(sid, f"doc:{docid}")
        scope = f"import:{document['input_type']}" if document else f"{docid}:{kind}"
        ikey = self.key(sid, f"idem:{scope}:{idem}")
        daily = f"aight:budget:{datetime.now(timezone.utc):%Y-%m-%d}"
        reservation = (self.settings.question_provider_tokens if kind == "question" else self.settings.operation_provider_tokens)
        for _ in range(5):
            with self.redis.pipeline() as pipe:
                try:
                    pipe.watch(skey, dkey, ikey, daily)
                    session_raw = pipe.get(skey)
                    session = json.loads(session_raw) if session_raw else None
                    if not session or session["expires_ms"] <= now_ms():
                        raise ServiceError("invalid_session", "Start a new temporary session.", 401)
                    existing = pipe.get(ikey)
                    if existing:
                        existing = json.loads(existing)
                        if existing["fingerprint"] != fingerprint:
                            raise ServiceError("idempotency_conflict", "Use a different key for different input.", 409)
                        self.document(sid, existing["response"]["document_id"])
                        return existing["response"], False
                    stored_doc = pipe.get(dkey)
                    doc = document or (json.loads(stored_doc) if stored_doc else None)
                    if not doc or doc["status"] == "deleted" or doc["expires_ms"] <= now_ms():
                        raise ServiceError("not_found", "This document is unavailable.", 404)
                    if not document and doc["status"] != "ready":
                        raise ServiceError("document_not_ready", "This document is not ready.", 409, True)
                    if session["outstanding"] >= self.settings.max_outstanding_operations:
                        raise ServiceError("session_limit_reached", "Wait for the current work to finish.", 429, True)
                    if document and session["documents_created"] >= self.settings.max_documents_per_session:
                        raise ServiceError("session_limit_reached", "This session has reached its document limit.", 429)
                    used_daily = int(pipe.get(daily) or 0)
                    if session["provider_tokens_reserved"] + reservation > self.settings.session_provider_tokens or used_daily + reservation > self.settings.daily_provider_tokens:
                        raise ServiceError("capacity_limited", "The processing budget is exhausted. Try a later session.", 429)
                    opid, created = identity("op"), iso(now_ms())
                    response = {"document_id": docid, "operation_id": opid, "status": "queued", "expires_at": session["expires_at"]}
                    operation = {"id": opid, "session_id": sid, "document_id": docid,
                                 "document_generation": doc["generation"], "job_id": opid,
                                 "kind": kind, "state": "queued", "stage": "queued", "attempt": 0,
                                 "attempt_token": None, "request": payload, "result": None, "error": None,
                                 "created_at": created, "updated_at": created,
                                 "expires_at": session["expires_at"], "expires_ms": session["expires_ms"]}
                    session["outstanding"] += 1
                    session["documents_created"] += int(document is not None)
                    session["provider_tokens_reserved"] += reservation
                    ttl = max(1, (session["expires_ms"] - now_ms()) // 1000)
                    job = Queue.prepare_data("aight_api.jobs.execute", (sid, opid), job_id=opid,
                                             timeout=self.settings.operation_timeout, ttl=ttl,
                                             result_ttl=ttl, failure_ttl=ttl, description="AIGht processing")
                    pipe.multi()
                    pipe.set(skey, packed(session), pxat=session["expires_ms"])
                    if document:
                        document["ingestion_operation_id"] = opid
                        pipe.set(dkey, packed(document), pxat=session["expires_ms"])
                    pipe.set(self.key(sid, f"op:{opid}"), packed(operation), pxat=session["expires_ms"])
                    pipe.sadd(self.key(sid, f"doc:{docid}:ops"), opid)
                    pipe.pexpireat(self.key(sid, f"doc:{docid}:ops"), session["expires_ms"])
                    pipe.set(ikey, packed({"fingerprint": fingerprint, "response": response}), pxat=session["expires_ms"])
                    pipe.set(daily, used_daily + reservation, ex=86_400)
                    self.queue.enqueue_many([job], pipeline=pipe)
                    pipe.execute()
                    return response, True
                except WatchError:
                    continue
        raise ServiceError("request_in_progress", "A concurrent request is being processed. Retry this key.", 409, True)

    def claim(self, sid: str, opid: str) -> tuple[dict, dict] | None:
        key = self.key(sid, f"op:{opid}")
        for _ in range(5):
            with self.redis.pipeline() as pipe:
                try:
                    pipe.watch(key, self.key(sid), self.key(sid, f"doc:{self.operation(sid, opid)['document_id']}"))
                    session = self.read(self.key(sid))
                    operation = self.operation(sid, opid)
                    document = self.document(sid, operation["document_id"])
                    if not session or session["expires_ms"] <= now_ms() or operation["state"] != "queued" or operation["document_generation"] != document["generation"]:
                        return None
                    operation.update(state="running", stage="extracting" if operation["kind"] == "ingestion" else "analyzing",
                                     attempt=operation["attempt"] + 1, attempt_token=secrets.token_hex(16), updated_at=iso(now_ms()))
                    pipe.multi()
                    pipe.set(key, packed(operation), pxat=operation["expires_ms"])
                    if operation["kind"] == "ingestion":
                        document["status"] = "processing"
                        pipe.set(self.key(sid, f"doc:{document['id']}"), packed(document), pxat=document["expires_ms"])
                    pipe.execute()
                    return operation, document
                except WatchError:
                    continue
                except ServiceError:
                    return None
        return None

    def finish(self, sid: str, operation: dict, result: dict | None = None,
               error: dict | None = None, document: dict | None = None) -> bool:
        final = dict(operation, state="failed" if error else "succeeded", stage="failed" if error else "complete",
                     result=result, error=error, updated_at=iso(now_ms()), capacity_released=True)
        current_doc = self.read(self.key(sid, f"doc:{operation['document_id']}"))
        # Preserve JSON arrays verbatim; Redis Lua's cjson re-encodes empty arrays as objects.
        document_json = packed({**current_doc, **document}) if current_doc and document is not None else ""
        return bool(self.redis.eval(FINALIZE, 3, self.key(sid), self.key(sid, f"doc:{operation['document_id']}"),
                                    self.key(sid, f"op:{operation['id']}"), operation["document_generation"],
                                    operation["attempt_token"], packed(final), document_json))

    def content(self, sid: str, docid: str) -> dict:
        document = self.document(sid, docid, ready=True)
        content = self.read(document.get("content_key", ""))
        if not content:
            raise ServiceError("dependency_unavailable", "Document data is unavailable. Import it again.", 503)
        return content

    def stage_content(self, sid: str, operation: dict, value: dict) -> str:
        key = self.key(sid, f"doc:{operation['document_id']}:candidate:{operation['attempt_token']}")
        self.redis.set(key, packed(value), pxat=operation["expires_ms"])
        return key

    def revoke_document(self, sid: str, docid: str) -> None:
        if not self.redis.eval(REVOKE, 3, self.key(sid, f"doc:{docid}"), self.key(sid),
                               self.key(sid, f"doc:{docid}:ops"), sid, secrets.token_hex(16), self.key(sid, "op:")):
            raise ServiceError("not_found", "This resource is unavailable.", 404)
        self.redis.sadd("aight:cleanup", f"{sid}/{docid}")

    def revoke_session(self, session: dict) -> None:
        with self.redis.pipeline(transaction=True) as pipe:
            pipe.delete(self.key(session["id"]), f"aight:token:{session['token_digest']}")
            pipe.sadd("aight:cleanup", f"{session['id']}/*")
            pipe.execute()
