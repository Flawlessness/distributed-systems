WORKER_PORT = 8080
MANAGER_URL = 'http://manager:8080'
ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789'

WORKER_TASK_URL = "/internal/api/worker/hash/crack/task"
WORKER_HEALTH_URL = "/health"
WORKER_PROGRESS_URL = "/progress"
MANAGER_PATCH_URL = "/internal/api/manager/hash/crack/request"