from typing import List

WORKER_URLS: List[str] = ['http://lab1-worker-1:8080', 'http://lab1-worker-2:8080', 'http://lab1-worker-3:8080']
MANAGER_PORT: int = 8080
RETRY_COUNT: int = 3
RETRY_TIMEOUT_SECONDS: int = 3
REQUEST_TIMEOUT: int = 30000

WORKER_HEALTH_URL = "/health"
WORKER_TASK_URL = "/internal/api/worker/hash/crack/task"
WORKER_PROGRESS_URL = "/progress"
MANAGER_CRACK_URL = "/api/hash/crack"
MANAGER_STATUS_URL = "/api/hash/status"
MANAGER_PATCH_URL = "/internal/api/manager/hash/crack/request"