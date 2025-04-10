import aiohttp
from aiohttp import web
import uuid
import time
import asyncio
import xml.etree.ElementTree as ET
import logging
from typing import Dict, Any, Optional
from config import *
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class Status(Enum):
    NEW = "NEW"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    ERROR = "ERROR"

class RequestStore:
    def __init__(self):
        self.requests: Dict[str, Dict[str, Any]] = {}
        self.lock: asyncio.Lock = asyncio.Lock()

    async def create_request(self, request_id: str, part_count: int) -> None:
        async with self.lock:
            self.requests[request_id] = {
                'status': Status.NEW.value,
                'results': [],
                'parts_received': 0,
                'part_count': part_count,
                'start_time': time.time(),
                'timeout': REQUEST_TIMEOUT
            }

    async def update_request(self, request_id: str, results: List[str], partial: str) -> None:
        async with self.lock:
            if request_id not in self.requests:
                return
            request = self.requests[request_id]
            if request['status'] == Status.IN_PROGRESS.value:
                for result in results:
                    if result not in request['results']:
                        request['results'].append(result)
                if partial == "False":
                    request['parts_received'] += 1
                    if request['parts_received'] >= request['part_count']:
                        request['status'] = Status.READY.value

    async def check_timeouts(self) -> None:
        async with self.lock:
            current_time = time.time()
            for req_id, req in self.requests.items():
                if req['status'] == Status.IN_PROGRESS.value:
                    if current_time - req['start_time'] > req['timeout']:
                        req['status'] = Status.ERROR.value

    async def get_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        async with self.lock:
            return self.requests.get(request_id)

    async def mark_worker_failed(self, request_id: str) -> None:
        async with self.lock:
            if request_id in self.requests:
                self.requests[request_id]['parts_received'] += 1
                self.requests[request_id]['status'] = Status.ERROR.value

class Manager:
    def __init__(self):
        self.request_store = RequestStore()
        self.request_queue = asyncio.Queue()

    async def check_worker_health(self, worker_url: str) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{worker_url}{WORKER_HEALTH_URL}") as response:
                    return response.status == 200
        except:
            return False

    async def process_requests(self) -> None:
        while True:
            try:
                request_data = self.request_queue.get_nowait()

                request_id = request_data['request_id']
                hash_target = request_data['hash']
                max_length = request_data['max_length']
                part_count = len(WORKER_URLS)

                request_data = await self.request_store.get_request(request_id)
                request_data["status"] = Status.IN_PROGRESS.value

                for part_number in range(part_count):
                    task_data = {
                        'request_id': request_id,
                        'hash': hash_target,
                        'max_length': max_length,
                        'part_number': part_number,
                        'part_count': part_count
                    }
                    asyncio.create_task(
                        self.safe_send_task(
                            WORKER_URLS[part_number],
                            task_data,
                            request_id
                        )
                    )
                while True:
                    if request_data["status"] in [Status.READY.value, Status.ERROR.value]:
                        self.request_queue.task_done()
                        if len(self.request_store.requests) > 1000:
                            self.request_store.requests.pop(0)
                        break
                    await asyncio.sleep(1)

            except asyncio.QueueEmpty:
                await asyncio.sleep(1)

    async def handle_crack_hash(self, request: web.Request) -> web.Response:
        for url in WORKER_URLS:
            health_check = False
            for _ in range(RETRY_COUNT + 1):
                if await self.check_worker_health(url):
                    health_check = True
                    break
                else:
                    logging.error(f"Worker {url} unavailable. Retry...")
                    await asyncio.sleep(RETRY_TIMEOUT_SECONDS)
            if not health_check:
                return web.json_response({'error': 'One or more workers are down'}, status=500)

        data = await request.json()
        hash_target = data.get('hash')
        max_length = data.get('maxLength')

        if not hash_target or not max_length:
            return web.json_response({'error': 'Missing hash or maxLength'}, status=400)

        request_id = str(uuid.uuid4())
        part_count = len(WORKER_URLS)
        await self.request_store.create_request(request_id, part_count)
        await self.request_queue.put({
            'request_id': request_id,
            'hash': hash_target,
            'max_length': max_length
        })
        print(f"put {request_id}")
        return web.json_response({'RequestId': request_id})

    async def safe_send_task(self, worker_url: str, task_data: Dict[str, Any], request_id: str) -> None:
        for _ in range(RETRY_COUNT + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{worker_url}{WORKER_TASK_URL}",
                        json=task_data
                    ) as response:
                        if response.status != 200:
                            logging.error(f"Worker {worker_url} failed for request {request_id}")
                        else:
                            return
            except Exception as e:
                logging.error(f"Task {request_id} failed for {worker_url}: {str(e)} \n Retry...")
                await asyncio.sleep(RETRY_TIMEOUT_SECONDS)
        logging.error(f"Task {request_id} failed for {worker_url} \n Maximum number of retry attempts reached")
        await self.request_store.mark_worker_failed(request_id)

    async def handle_get_status(self, request: web.Request) -> web.Response:
        request_id = request.query.get('requestId')
        if not request_id:
            return web.json_response({'error': 'Missing requestId'}, status=400)

        request_data = await self.request_store.get_request(request_id)
        if not request_data:
            return web.json_response({'error': 'Invalid requestId'}, status=404)

        await self.request_store.check_timeouts()

        request_data = await self.request_store.get_request(request_id)

        part_count = len(WORKER_URLS)

        total_percentage = 0
        if request_data['status'] == Status.IN_PROGRESS.value:
            for part_number in range(part_count):
                percent = await self.get_progress(request_id, WORKER_URLS[part_number])
                if percent:
                    total_percentage += float(percent)
                else:
                    total_percentage = 0
                    break
            total_percentage = total_percentage / 3 * 100
        elif request_data['status'] == Status.NEW.value:
            total_percentage = 0
        elif request_data['status'] == Status.READY.value:
            total_percentage = 100

        status = request_data['status']
        part_count = request_data['part_count']
        parts_received = request_data['parts_received']
        progress_str = f"{total_percentage:.0f}%"
        results = request_data['results']

        response_data = {
            'status': status,
            'progress': progress_str,
            'partial_result': results
        }

        if status == Status.READY.value:
            response_data['data'] = results
            del response_data['partial_result']

        return web.json_response(response_data)

    async def get_progress(self, request_id: str, worker_url: str) -> Optional[str]:
        for _ in range(RETRY_COUNT + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{worker_url}{WORKER_PROGRESS_URL}"
                    ) as response:
                        if response.status != 200:
                            logging.error(f"Worker {worker_url} failed for request")
                        else:
                            return await response.text()
            except Exception as e:
                logging.error(f"Get progress {request_id} failed for {worker_url}: {str(e)} \n Retry...")
                await asyncio.sleep(RETRY_TIMEOUT_SECONDS)
        logging.error(f"Get progress {request_id} failed for {worker_url} \n Maximum number of retry attempts reached")
        await self.request_store.mark_worker_failed(request_id)
        return None

    async def handle_patch_request(self, request: web.Request) -> web.Response:
        try:
            data = await request.text()
            root = ET.fromstring(data)
            request_id = root.findtext('RequestId')
            part_number = int(root.findtext('PartNumber'))
            part_count = int(root.findtext('PartCount'))
            results = [elem.text for elem in root.findall('Results/Result')]
            partial = root.findtext('Partial')
            await self.request_store.update_request(request_id, results, partial)
            return web.Response(status=200)
        except Exception as e:
            return web.Response(status=400)

    async def background_timeout_checker(self, app: web.Application) -> None:
        while True:
            await asyncio.sleep(10)
            await self.request_store.check_timeouts()

    async def start_background_tasks(self, app: web.Application) -> None:
        app['process_requests'] = asyncio.create_task(self.process_requests())
        app['background_timeout_checker'] = asyncio.create_task(self.background_timeout_checker(app))

    async def cleanup_background_tasks(self, app: web.Application) -> None:
        app['process_requests'].cancel()
        await app['process_requests']
        app['background_timeout_checker'].cancel()
        await app['background_timeout_checker']
