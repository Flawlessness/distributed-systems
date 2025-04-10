RABBIT_HOST = "rabbitmq"
RABBIT_PORT = "5672"
RABBIT_USER = "admin"
RABBIT_PASS = "admin123"
RABBIT_MANAGER_QUEUE = "manager_queue"
RABBIT_WORKER_TASK_QUEUE = "task_queue"
RABBIT_WORKER_RESULTS_QUEUE = "results_queue"

WORKER_PORT = 8080
GET_TIMEOUT_SECONDS: int = 1
MANAGER_URL = 'http://manager:8080'
ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789'

WORKER_TASK_URL = "/internal/api/worker/hash/crack/task"
WORKER_HEALTH_URL = "/health"
WORKER_PROGRESS_URL = "/progress"
MANAGER_PATCH_URL = "/internal/api/manager/hash/crack/request"