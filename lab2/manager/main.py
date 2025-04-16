from manager import *

if __name__ == '__main__':
    manager = Manager()
    app = web.Application()

    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods=["POST", "GET", "OPTIONS"],  # Include OPTIONS
        )
    })

    app.router.add_post(MANAGER_CRACK_URL, manager.handle_crack_hash)
    app.router.add_get(MANAGER_STATUS_URL, manager.handle_get_status)

    for route in list(app.router.routes()):
        cors.add(route)

    app.on_startup.append(manager.start_background_tasks)
    app.on_cleanup.append(manager.cleanup_background_tasks)

    web.run_app(app, port=MANAGER_PORT)