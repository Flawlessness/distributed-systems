from motor.motor_asyncio import AsyncIOMotorClient
from config import *
from typing import Dict, Any, Optional, List
import time

class MongoRequestStore:
    def __init__(self):
        self.client = None
        self.db = None
        self.collection = None

    async def connect(self):
        self.client = AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[MONGO_DB_NAME]
        self.collection = self.db[MONGO_COLLECTION_NAME]
        await self._create_indexes()

    async def _create_indexes(self):
        await self.collection.create_index("request_id", unique=True)
        await self.collection.create_index("status")
        await self.collection.create_index("start_time")

    async def create_request(self, request_id: str, part_count: int) -> None:
        document = {
            "request_id": request_id,
            "status": "NEW",
            "results": [],
            "parts_received": 0,
            "part_count": part_count,
            "start_time": time.time(),
            "timeout": REQUEST_TIMEOUT,
            "delivery_tag": 0
        }
        await self.collection.insert_one(document)

    async def update_request(self, request_id: str, results: List[str], partial: str) -> None:
        request_data = await self.get_request(request_id)
        update_op = {
            "$addToSet": {"results": {"$each": results}},
            "$inc": {"parts_received": 1} if partial == "False" else {},
            "$set": {"status": Status.READY.value} if
                request_data["parts_received"] == (request_data["part_count"] - 1)
                and partial == "False" else {}
        }
        await self.collection.update_one(
            {"request_id": request_id},
            update_op
        )

    async def set_status(self, request_id: str, status: str) -> None:
        await self.collection.update_one(
            {"request_id": request_id},
            {
                "$set": {"status": status}
            }
        )

    async def set_delivery_tag(self, request_id: str, delivery_tag: int) -> None:
        await self.collection.update_one(
            {"request_id": request_id},
            {
                "$set": {"delivery_tag": delivery_tag}
            }
        )

    async def check_timeouts(self) -> None:
        current_time = time.time()
        await self.collection.update_many(
            {
                "status": "IN_PROGRESS",
                "start_time": {"$lt": current_time - REQUEST_TIMEOUT}
            },
            {"$set": {"status": "ERROR"}}
        )

    async def get_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        return await self.collection.find_one({"request_id": request_id})

    async def mark_worker_failed(self, request_id: str) -> None:
        await self.collection.update_one(
            {"request_id": request_id},
            {
                "$inc": {"parts_received": 1},
                "$set": {"status": "ERROR"}
            }
        )

    async def close(self):
        if self.client:
            self.client.close()