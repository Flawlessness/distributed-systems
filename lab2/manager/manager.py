from time import sleep

import aiohttp_cors
import aiohttp
from aiohttp import web
import uuid
import time
import asyncio
import xml.etree.ElementTree as ET
import logging
from typing import Dict, Any, Optional
from config import *
from mongo_store import MongoRequestStore
from rabbit import RabbitMQClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class Manager:
    def __init__(self):
        self.request_store = MongoRequestStore()
        self.manager_queue = RabbitMQClient(
            RABBIT_HOST,
            RABBIT_PORT,
            RABBIT_USER,
            RABBIT_PASS,
            RABBIT_MANAGER_QUEUE
        )
        self.worker_task_queue = RabbitMQClient(
            RABBIT_HOST,
            RABBIT_PORT,
            RABBIT_USER,
            RABBIT_PASS,
            RABBIT_WORKER_TASK_QUEUE
        )
        self.worker_results_queue = RabbitMQClient(
            RABBIT_HOST,
            RABBIT_PORT,
            RABBIT_USER,
            RABBIT_PASS,
            RABBIT_WORKER_RESULTS_QUEUE
        )
        self.manager_queue.connect()
        self.worker_task_queue.connect()
        self.worker_results_queue.connect()

        self.workers_list = {}
        self.task_data = {}

    async def check_worker_health(self, worker_url: str):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{worker_url}{WORKER_HEALTH_URL}") as response:
                    if response.status == 200:
                        return await response.text()
                    else:
                        return None
        except:
            return None

    async def process_requests(self) -> None:
        while True:
            try:
                request_data, delivery_tag = await self.manager_queue.get()
                if not request_data:
                    await asyncio.sleep(GET_TIMEOUT_SECONDS)
                    continue

                request_id = request_data['request_id']
                hash_target = request_data['hash']
                max_length = request_data['max_length']
                part_count = len(WORKER_URLS)

                await self.request_store.connect()
                request_data = await self.request_store.get_request(request_id)

                if request_data["status"] != Status.NEW.value:
                    while True:
                        request_data = await self.request_store.get_request(request_id)
                        if request_data["status"] in [Status.READY.value, Status.ERROR.value]:
                            break
                        await asyncio.sleep(GET_TIMEOUT_SECONDS)
                    self.manager_queue.ack(delivery_tag)
                    continue

                await self.request_store.set_status(request_id, Status.IN_PROGRESS.value)

                for part_number in range(part_count):
                    task_data = {
                        'request_id': request_id,
                        'hash': hash_target,
                        'max_length': max_length,
                        'part_number': part_number,
                        'part_count': part_count
                    }
                    self.task_data = task_data
                    await self.worker_task_queue.push(task_data)

                while True:
                    request_data = await self.request_store.get_request(request_id)
                    if request_data["status"] in [Status.READY.value, Status.ERROR.value]:
                        self.manager_queue.ack(delivery_tag)
                        break
                    try:
                        self.manager_queue.channel.queue_declare(queue=self.manager_queue.queue_name,
                                                                        passive=True)
                    except Exception as e1:
                        logging.error(f"Wait connect...")
                        break
                    await asyncio.sleep(GET_TIMEOUT_SECONDS)
            except Exception as e:
                logging.error(f"Wait connect process_requests...")
                await asyncio.sleep(GET_TIMEOUT_SECONDS)

    async def process_results(self) -> None:
        while True:
            try:
                result_data = await self.worker_results_queue.get_string(ack=True)
                if not result_data:
                    await asyncio.sleep(GET_TIMEOUT_SECONDS)
                    continue

                root = ET.fromstring(result_data)
                request_id = root.findtext('RequestId')
                part_number = int(root.findtext('PartNumber'))
                part_count = int(root.findtext('PartCount'))
                results = [elem.text for elem in root.findall('Results/Result')]
                partial = root.findtext('Partial')
                await self.request_store.connect()
                await self.request_store.update_request(request_id, results, partial)

            except Exception as e:
                logging.error(f"Wait connect process_results...")
                await asyncio.sleep(GET_TIMEOUT_SECONDS)

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
        await self.request_store.connect()
        await self.request_store.create_request(request_id, part_count)
        await self.manager_queue.push({
            'request_id': request_id,
            'hash': hash_target,
            'max_length': max_length
        })

        return web.json_response({'RequestId': request_id})

    async def handle_get_status(self, request: web.Request) -> web.Response:
        request_id = request.query.get('requestId')
        if not request_id:
            return web.json_response({'error': 'Missing requestId'}, status=400)

        await self.request_store.connect()

        request_data = await self.request_store.get_request(request_id)
        if not request_data:
            return web.json_response({'error': 'Invalid requestId'}, status=404)

        await self.request_store.check_timeouts()

        part_count = len(WORKER_URLS)

        total_percentage = 0
        if request_data['status'] == Status.IN_PROGRESS.value:
            for part_number in range(part_count):
                percent = await self.get_progress(request_id, WORKER_URLS[part_number])
                logging.info(f"Gen: {percent}")
                total_percentage += float(percent)
            total_percentage -= request_data['parts_received']
            logging.info(f"parts_received: {request_data['parts_received'] / request_data['part_count']}")

            total_percentage = ((total_percentage / len(WORKER_URLS)
                                + request_data['parts_received']/request_data['part_count'])
                                * 100)
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
        return "0"

    async def workers_monitoring(self):
        while True:
            for url in WORKER_URLS:
                part_number = None
                for _ in range(RETRY_COUNT + 1):
                    part_number = await self.check_worker_health(url)
                    if part_number:
                        break
                    else:
                        logging.error(f"Worker {url} unavailable. Retry...")
                        await asyncio.sleep(RETRY_TIMEOUT_SECONDS)

                if part_number:
                    self.workers_list[url] = part_number
                else:
                    if self.workers_list[url]:
                        logging.error(f"Worker {url} unavailable. Resubmitting a task...")
                        self.task_data["part_number"] = int(self.workers_list[url])
                        await self.worker_task_queue.push(self.task_data)
                        self.workers_list[url] = None


            await asyncio.sleep(HEALTHCHECK_SECONDS)

    async def background_timeout_checker(self, app: web.Application) -> None:
        while True:
            await asyncio.sleep(HEALTHCHECK_SECONDS)
            await self.request_store.check_timeouts()

    async def start_background_tasks(self, app: web.Application) -> None:
        app['process_requests'] = asyncio.create_task(self.process_requests())
        app['process_results'] = asyncio.create_task(self.process_results())
        app['workers_monitoring'] = asyncio.create_task(self.workers_monitoring())
        app['background_timeout_checker'] = asyncio.create_task(self.background_timeout_checker(app))

    async def cleanup_background_tasks(self, app: web.Application) -> None:
        app['process_requests'].cancel()
        await app['process_requests']
        app['process_results'].cancel()
        await app['process_results']
        app['workers_monitoring'].cancel()
        await app['workers_monitoring']
        app['background_timeout_checker'].cancel()
        await app['background_timeout_checker']
