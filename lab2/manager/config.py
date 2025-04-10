from enum import Enum
from typing import List

class Status(Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    ERROR = "ERROR"

RABBIT_HOST = "rabbitmq"
RABBIT_PORT = "5672"
RABBIT_USER = "admin"
RABBIT_PASS = "admin123"
RABBIT_MANAGER_QUEUE = "manager_queue"
RABBIT_WORKER_TASK_QUEUE = "task_queue"
RABBIT_WORKER_RESULTS_QUEUE = "results_queue"

MONGO_URI: str = "mongodb://mongo-primary:27017,mongo-secondary1:27017,mongo-secondary2:27017/?replicaSet=rs0"
MONGO_DB_NAME: str = "crackhash"
MONGO_COLLECTION_NAME: str = "requests"

WORKER_URLS: List[str] = ['http://lab1-worker-1:8080', 'http://lab1-worker-2:8080', 'http://lab1-worker-3:8080']
MANAGER_PORT: int = 8080
RETRY_COUNT: int = 3
RETRY_TIMEOUT_SECONDS: int = 1
GET_TIMEOUT_SECONDS: int = 1
HEALTHCHECK_SECONDS: int = 3
REQUEST_TIMEOUT: int = 30000

WORKER_HEALTH_URL = "/health"
WORKER_TASK_URL = "/internal/api/worker/hash/crack/task"
WORKER_PROGRESS_URL = "/progress"
MANAGER_CRACK_URL = "/api/hash/crack"
MANAGER_STATUS_URL = "/api/hash/status"
MANAGER_PATCH_URL = "/internal/api/manager/hash/crack/request"