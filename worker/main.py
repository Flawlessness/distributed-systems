from aiohttp import web
import hashlib
import xml.etree.ElementTree as ET
import asyncio
import requests
from typing import List
from config import *

class Calculate:
    def __init__(self):
        self.current_tasks: int = 0
        self.total_tasks: int = 0

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
                    self.send_response(request_id, part_number, part_count, [word], partial=True)
                self.current_tasks += 1
                if self.current_tasks % 10000 == 0:
                    await asyncio.sleep(0)
        return results

    def send_response(self, request_id: str, part_number: int, part_count: int, results: List[str], partial: bool = False) -> None:
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

        try:
            response = requests.patch(
                f"{MANAGER_URL}{MANAGER_PATCH_URL}",
                data=xml_data,
                headers={'Content-Type': 'application/xml'}
            )
            if response.status_code != 200:
                print(f"Error: Received status code {response.status_code}")  # Log error
        except Exception as e:
            print(f"Exception occurred: {e}")  # Log exception

class Worker:
    def __init__(self):
        self.calculate = Calculate()

    async def handle_worker_task(self, request: web.Request) -> web.Response:
        data = await request.json()
        request_id = data.get('request_id')
        hash_target = data.get('hash')
        max_length = data.get('max_length')
        part_number = data.get('part_number')
        part_count = data.get('part_count')

        if not all([request_id, hash_target, max_length is not None, part_number is not None, part_count is not None]):
            return web.Response(status=400)

        results = await self.calculate.process_task(request_id, hash_target, max_length, part_number, part_count)
        self.calculate.send_response(request_id, part_number, part_count, results)

        return web.Response(status=200)

    async def handle_progress(self, request: web.Request) -> web.Response:
        if self.calculate.total_tasks != 0:
            return web.Response(text=f"{self.calculate.current_tasks/self.calculate.total_tasks}")
        else:
            return web.Response(text=f"0")

    async def health_check(self, request: web.Request) -> web.Response:
        return web.Response(text="OK")

if __name__ == '__main__':
    app = web.Application()
    worker = Worker()

    app.router.add_post(WORKER_TASK_URL, worker.handle_worker_task)
    app.router.add_get(WORKER_HEALTH_URL, worker.health_check)
    app.router.add_get(WORKER_PROGRESS_URL, worker.handle_progress)
    web.run_app(app, port=WORKER_PORT)