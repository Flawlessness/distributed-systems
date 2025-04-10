from worker import *

if __name__ == '__main__':
    app = web.Application()
    worker = Worker()

    app.router.add_post(WORKER_TASK_URL, worker.handle_worker_task)
    app.router.add_get(WORKER_HEALTH_URL, worker.health_check)
    app.router.add_get(WORKER_PROGRESS_URL, worker.handle_progress)
    web.run_app(app, port=WORKER_PORT)