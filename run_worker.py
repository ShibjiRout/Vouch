from app.services.redis_service import connection
from rq import SimpleWorker, Queue

queue = Queue(connection=connection)
SimpleWorker([queue], connection=connection).work()
