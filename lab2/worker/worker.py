from aiohttp import web
import hashlib
import xml.etree.ElementTree as ET
import asyncio
import requests
from typing import List
from config import *
from rebbit import RabbitMQClient
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class WorkerHelper:
    def __init__(self, worker_results_queue: RabbitMQClient = None):
        self.current_tasks: int = 0
        self.total_tasks: int = 0
        self.worker_results_queue = worker_results_queue

    def num_to_word(self, num: int, length: int) -> str:
        chars = ""
        for _ in range(length):
            num, rem = divmod(num, 36)
            chars += ALPHABET[rem]
        return chars

    async def process_task(self, request_id: str, hash_target: str, max_length: int, part_number: int, part_count: int) -> List[str]:
        results: List[str] = []
        self.current_tasks = 0
        self.total_tasks = 0
        for length in range(1, max_length + 1):
            self.total_tasks += 36 ** length
        self.total_tasks /= part_count

        for length in range(1, max_length + 1):
            total = 36 ** length
            per_part, rem = divmod(total, part_count)
            if part_number < rem:
                start = part_number * (per_part + 1)
                end = start + (per_part + 1)
            else:
                start = rem * (per_part + 1) + (part_number - rem) * per_part
                end = start + per_part

            for word_num in range(start, end):
                word = self.num_to_word(word_num, length)
                md5 = hashlib.md5(word.encode()).hexdigest()
                if md5 == hash_target:
                    await self.send_response(request_id, part_number, part_count, [word], partial=True)
                self.current_tasks += 1
                if self.current_tasks % 10000 == 0:
                    await asyncio.sleep(0)
        return results

    async def send_response(self, request_id: str, part_number: int, part_count: int, results: List[str], partial: bool = False) -> None:
        root = ET.Element('CrackResult')
        ET.SubElement(root, 'RequestId').text = request_id
        ET.SubElement(root, 'PartNumber').text = str(part_number)
        ET.SubElement(root, 'PartCount').text = str(part_count)

        results_elem = ET.SubElement(root, 'Results')
        for res in results:
            ET.SubElement(results_elem, 'Result').text = res

        if partial:
            ET.SubElement(root, 'Partial').text = "True"
        else:
            ET.SubElement(root, 'Partial').text = "False"

        xml_data = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding='unicode')

        logging.info(f"Send result {xml_data}")
        try:
            await self.worker_results_queue.push_string(xml_data)
        except Exception as e:
            logging.error(f"Exception occurred: {e}")

class Worker:
    def __init__(self):
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
        self.worker_task_queue.connect()
        self.worker_results_queue.connect()

        self.worker_helper = WorkerHelper(self.worker_results_queue)
        self.part_number = None

    async def process_task(self) -> None:
        while True:
            try:
                task_data = await self.worker_task_queue.get(ack=True)
                if not task_data:
                    await asyncio.sleep(GET_TIMEOUT_SECONDS)
                    continue
                logging.info(f"GET TASK {task_data}")
                request_id = task_data.get('request_id')
                hash_target = task_data.get('hash')
                max_length = task_data.get('max_length')
                part_number = task_data.get('part_number')
                part_count = task_data.get('part_count')

                self.part_number = part_number

                results = await self.worker_helper.process_task(request_id, hash_target, max_length, part_number,
                                                                part_count)

                await self.worker_helper.send_response(request_id, part_number, part_count, results)

            except Exception as e:
                logging.error(f"Exception worker.process_task {e}")
                await asyncio.sleep(GET_TIMEOUT_SECONDS)

    async def handle_progress(self, request: web.Request) -> web.Response:
        if self.worker_helper.total_tasks != 0:
            logging.info(f"worker: {self.worker_helper.current_tasks/self.worker_helper.total_tasks}")
            return web.Response(text=f"{self.worker_helper.current_tasks/self.worker_helper.total_tasks}")
        else:
            return web.Response(text=f"0")

    async def health_check(self, request: web.Request) -> web.Response:
        return web.Response(text=f"{self.part_number}")

    async def start_background_tasks(self, app: web.Application) -> None:
        app['process_task'] = asyncio.create_task(self.process_task())

    async def cleanup_background_tasks(self, app: web.Application) -> None:
        app['process_task'].cancel()
        await app['process_task']
