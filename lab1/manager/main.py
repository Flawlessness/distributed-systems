from manager import *

if __name__ == '__main__':
    manager = Manager()
    app = web.Application()
    app.router.add_post(MANAGER_CRACK_URL, manager.handle_crack_hash)
    app.router.add_get(MANAGER_STATUS_URL, manager.handle_get_status)
    app.router.add_patch(MANAGER_PATCH_URL, manager.handle_patch_request)

    app.on_startup.append(manager.start_background_tasks)
    app.on_cleanup.append(manager.cleanup_background_tasks)

    web.run_app(app, port=MANAGER_PORT)