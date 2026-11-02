import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from redis import Redis
from rq import Queue, Worker
from rq.serializers import JSONSerializer
from rq.worker import SpawnWorker
from aight_api.config import settings

if __name__ == "__main__":
    connection = Redis.from_url(settings.redis_url)
    kind = SpawnWorker if sys.platform == "win32" else Worker
    worker = kind([Queue("aight", connection=connection, serializer=JSONSerializer)], connection=connection, serializer=JSONSerializer)
    worker.work(with_scheduler=False)
