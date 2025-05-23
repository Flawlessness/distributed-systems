import json
import uuid
from time import sleep

import pika
from typing import Dict, Any, Optional, Union
from pika.connection import Connection
from pika.channel import Channel
import logging
import asyncio
from config import *

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class RabbitMQClient:
    """RabbitMQ client for sending and receiving dictionaries."""

    MessageType = Dict[str, Any]  # Type alias for message dictionaries

    def __init__(
            self,
            host: str = 'rabbitmq',
            port: int = 5672,
            username: str = 'admin',
            password: str = 'admin123',
            queue_name: str = 'default_queue'
    ):
        """Initialize RabbitMQ client with connection parameters."""
        self.connection_params = pika.ConnectionParameters(
            host=host,
            port=port,
            credentials=pika.PlainCredentials(username, password),
            heartbeat=60000,
            blocked_connection_timeout=30000
        )
        self.queue_name = queue_name
        self.connection: Optional[Connection] = None
        self.channel: Optional[Channel] = None

    def __enter__(self):
        """Context manager entry - establishes connection."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes connection."""
        self.close()

    def connect(self) -> None:
        """Establish connection and channel."""
        self.connection = pika.BlockingConnection(self.connection_params)
        self.channel = self.connection.channel()
        self.channel.queue_declare(
            queue=self.queue_name,
            durable=True
        )

    def close(self) -> None:
        """Close connection if it exists."""
        if self.connection and self.connection.is_open:
            self.connection.close()

    async def push(self, message: MessageType) -> bool:
        """
        Push a dictionary to the queue.

        Args:
            message: Dictionary to send

        Returns:
            bool: True if message was sent successfully
        """
        connect = True
        try:
            self.channel.queue_declare(queue=self.queue_name, passive=True)
        except Exception as e:
            logging.error(f"Connection not established...")
            connect = False
        if not connect:
            while True:
                try:
                    self.connect()
                    if self.channel and self.channel.is_open:
                        logging.info(f"Connection done")
                        break
                except Exception as e:
                    logging.error(f"Wait connect()")
                    await asyncio.sleep(GET_TIMEOUT_SECONDS)

        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=self.queue_name,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    content_type='application/json',
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
                )
            )
            return True
        except (pika.exceptions.AMQPError, json.JSONDecodeError) as e:
            logging.error(f"Failed to send message: {e}")
            return False

    async def get(self, ack: bool = False):
        """
        Get a single message from the queue.

        Args:
            :param ack: If True, automatically acknowledge receipt

        Returns:
            Optional dictionary with message content or None if queue is empty
        """
        connect = True
        try:
            self.channel.queue_declare(queue=self.queue_name, passive=True)
        except Exception as e:
            logging.error(f"Connection not established...")
            connect = False
        if not connect:
            while True:
                try:
                    self.connect()
                    if self.channel and self.channel.is_open:
                        logging.info(f"Connection done")
                        break
                except Exception as e:
                    logging.error(f"Wait connect()")
                    await asyncio.sleep(GET_TIMEOUT_SECONDS)

        method_frame, properties, body = self.channel.basic_get(
            queue=self.queue_name,
            auto_ack=ack
        )

        if not method_frame:
            return None, None

        try:
            if properties.content_type != 'application/json':
                raise ValueError("Non-JSON message received")

            message = json.loads(body.decode())
            if not isinstance(message, dict):
                raise ValueError("Message is not a dictionary")

            return message, method_frame.delivery_tag

        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
            logging.error(f"Failed to process message: {e}")
            self.channel.basic_nack(method_frame.delivery_tag, requeue=False)
            return None, None

    async def get_string(self, ack: bool = False) -> Optional[str]:
        """
        Get a single message from the queue.

        Args:
            :param ack: If True, automatically acknowledge receipt

        Returns:
            Optional dictionary with message content or None if queue is empty
        """
        connect = True
        try:
            self.channel.queue_declare(queue=self.queue_name, passive=True)
        except Exception as e:
            logging.error(f"Connection not established...")
            connect = False
        if not connect:
            while True:
                try:
                    self.connect()
                    if self.channel and self.channel.is_open:
                        logging.info(f"Connection done")
                        break
                except Exception as e:
                    logging.error(f"Wait connect()")
                    await asyncio.sleep(GET_TIMEOUT_SECONDS)

        method_frame, properties, body = self.channel.basic_get(
            queue=self.queue_name,
            auto_ack=ack
        )
        if not method_frame:
            return None

        return body.decode()

    def ack(self, delivery_tag: int):
        self.channel.basic_ack(delivery_tag)
