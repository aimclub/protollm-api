"""RabbitMQ implementation of :pyclass:`protollm_api.object_interface.message_queue.base.BaseMessageQueue`.

Changes in this revision
------------------------
* **Robust `get()` implementation** – handles cases where
  ``channel.basic_get`` returns ``None`` or ``(None, None, None)`` and supports
  the *timeout* parameter (simple polling with ``time.sleep``).

The rest of the adapter remains unchanged.
"""
import json
import logging
import subprocess
import threading
import time
from typing import Any, Callable, Optional

import pika
from pika import BasicProperties, BlockingConnection, ConnectionParameters, PlainCredentials

from .base import BaseMessageQueue, ReceivedMessage

log = logging.getLogger(__name__)

import requests
from requests.auth import HTTPBasicAuth

class RabbitMQQueue(BaseMessageQueue):  # noqa: WPS230
    """Synchronous RabbitMQ adapter."""

    backend_name = "rabbitmq"

    # ------------------------------------------------------------------
    # Construction / connection
    # ------------------------------------------------------------------
    def __init__(  # noqa: WPS211
        self,
        *,
        host: str = "localhost",
        port: int = 5672,
        api_port: int = 15672,
        virtual_host: str = "/",
        username: str = "guest",
        password: str = "guest",
        heartbeat: int | None = 60,
        blocked_connection_timeout: int | None = 30,
    ) -> None:
        self._params = ConnectionParameters(
            host=host,
            port=port,
            virtual_host=virtual_host,
            credentials=PlainCredentials(username, password),
            heartbeat=heartbeat,
            blocked_connection_timeout=blocked_connection_timeout,
        )
        self._connection: BlockingConnection | None = None
        self._channel: pika.channel.Channel | None = None
        self._consumer_tags: list[str] = []
        self._consume_thread: threading.Thread | None = None

        self._api_url = f"http://{host}:{api_port}/api"
        self._http_auth = HTTPBasicAuth(username, password)

    # ------------------------------------------------------------------
    # Base overrides
    # ------------------------------------------------------------------
    def connect(self) -> None:  # noqa: D401
        if self._connection and self._connection.is_open:
            return  # already connected
        log.debug("Connecting to RabbitMQ → %s", self._params.host)
        self._connection = BlockingConnection(self._params)
        self._channel = self._connection.channel()

    def close(self) -> None:  # noqa: D401
        if not self._connection:
            return
        for tag in self._consumer_tags:
            try:
                self._channel.basic_cancel(tag)
            except Exception:  # noqa: BLE001
                log.exception("Failed to cancel consumer %s", tag)
        if self._channel and self._channel.is_open:
            self._channel.close()
        if self._connection.is_open:
            self._connection.close()
        self._connection = None
        self._channel = None

    # ------------------------------------------------------------------
    # Queue declaration
    # ------------------------------------------------------------------
    def declare_queue(  # noqa: D401, WPS211
        self,
        name: str,
        *,
        durable: bool = True,
        auto_delete: bool = False,
        max_priority: int | None = None,
        **kwargs: Any,
    ) -> None:
        assert self._channel, "connect() must be called first"
        arguments: dict[str, Any] | None = None
        if max_priority is not None:
            arguments = {"x-max-priority": int(max_priority)}
        self._channel.queue_declare(
            queue=name,
            durable=durable,
            auto_delete=auto_delete,
            arguments=arguments,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------
    def publish(  # noqa: WPS211
        self,
        queue: str,
        task: dict,
        *,
        priority: int | None = None,
        routing_key: str | None = None,
        headers: dict[str, Any] | None = None,
        persistent: bool = True,
        **kwargs: Any,
    ) -> None:
        assert self._channel, "connect() must be called first"
        # body: bytes = task.encode() if isinstance(task, str) else task
        properties = BasicProperties(
            priority=priority,
            headers=headers,
            delivery_mode=2 if persistent else 1,
        )
        self._channel.basic_publish(
            exchange="",
            routing_key=routing_key or queue,
            body=json.dumps(task),
            properties=properties,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Consumption helpers
    # ------------------------------------------------------------------
    def _translate_message(self, method, props, body) -> ReceivedMessage:  # noqa: D401, N802, WPS110
        return ReceivedMessage(
            body=body,
            delivery_tag=method.delivery_tag,
            headers=getattr(props, "headers", {}) or {},
            routing_key=method.routing_key,
            priority=getattr(props, "priority", None),
        )

    def get(  # noqa: D401, WPS211
        self,
        queue: str,
        *,
        timeout: float | None = None,
        auto_ack: bool = False,
        **kwargs: Any,
    ) -> Optional[ReceivedMessage]:
        """Fetch one task with optional *timeout* (seconds)."""
        assert self._channel, "connect() must be called first"
        start = time.monotonic()
        while True:
            result = self._channel.basic_get(queue=queue, auto_ack=auto_ack)
            if result:
                # pika 1.x: (method, header, body) – method=None when queue empty
                if isinstance(result, tuple):
                    method = result[0]
                    if method is not None:
                        return self._translate_message(*result)
                else:  # some custom adapter could return object
                    method = result.method_frame  # type: ignore[attr-defined]
                    if method is not None:
                        return self._translate_message(
                            method,
                            result.properties,  # type: ignore[attr-defined]
                            result.body,  # type: ignore[attr-defined]
                        )
            # No task yet
            if timeout is not None and (time.monotonic() - start) >= timeout:
                return None
            time.sleep(0.1)

    def consume(  # noqa: D401, WPS211
        self,
        queue: str,
        callback: Callable[[ReceivedMessage], None],
        *,
        auto_ack: bool = False,
        prefetch: int = 1,
        **kwargs: Any,
    ) -> None:
        assert self._channel, "connect() must be called first"
        self._channel.basic_qos(prefetch_count=prefetch)

        def _on_message(ch, method, props, body):  # noqa: D401, N802
            msg = self._translate_message(method, props, body)
            callback(msg)
            if auto_ack is False:
                # Application must ack/nack explicitly
                pass

        tag = self._channel.basic_consume(queue=queue, on_message_callback=_on_message, auto_ack=auto_ack)
        self._consumer_tags.append(tag)

        def _start_consuming():  # noqa: D401
            try:
                self._channel.start_consuming()
            except KeyboardInterrupt:
                pass

        self._consume_thread = threading.Thread(target=_start_consuming, daemon=True)
        self._consume_thread.start()
        self._consume_thread.join()

    # ------------------------------------------------------------------
    # Ack / nack
    # ------------------------------------------------------------------
    def ack(self, delivery_tag: Any) -> None:  # noqa: D401
        assert self._channel, "connect() must be called first"
        self._channel.basic_ack(delivery_tag=delivery_tag)

    def nack(self, delivery_tag: Any, *, requeue: bool = True) -> None:  # noqa: D401
        assert self._channel, "connect() must be called first"
        self._channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue)

    # ------------------------------------------------------------------
    # Queue
    # ------------------------------------------------------------------
    def list_queues(self, timeout: float = 5.0) -> list[str]:
        url = f"{self._api_url}/queues"
        try:
            response = requests.get(url, auth=self._http_auth, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"RabbitMQ HTTP API request error: {e}")

        return [q["name"] for q in response.json()]

    def get_queue_info(self, queue_name: str, timeout: float = 5.0) -> dict:
        vhost_encoded = requests.utils.quote(self._params.virtual_host, safe='')
        url = f"{self._api_url}/queues/{vhost_encoded}/{queue_name}"

        try:
            response = requests.get(url, auth=self._http_auth, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"RabbitMQ HTTP API request error: {e}")

        return response.json()

    def peek_queue_messages(self, queue_name: str, count: int = 5, timeout: float = 5.0) -> list[dict]:
        vhost_encoded = requests.utils.quote(self._params.virtual_host, safe='')
        url = f"{self._api_url}/queues/{vhost_encoded}/{queue_name}/get"
        payload = {
            "count": count,
            "ackmode": "ack_requeue_true",
            "encoding": "auto",
            "truncate": 50000
        }
        try:
            response = requests.post(
                url,
                json=payload,
                auth=self._http_auth,
                timeout=timeout
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"RabbitMQ HTTP API request error: {e}")
        return response.json()

    def get_message_position_by_id(self, queue_name: str, job_id: str, batch_size: int = 100, timeout: float = 5.0) -> dict:
        position = 0
        while True:
            try:
                messages = self.peek_queue_messages(queue_name=queue_name, count=batch_size, timeout=timeout)
            except Exception as e:
                raise RuntimeError(f"Error during message peek: {e}")
            if not messages:
                break
            for index, raw_msg in enumerate(messages):
                raw_payload = raw_msg.get("payload")
                if isinstance(raw_payload, str):
                    try:
                        payload = json.loads(raw_payload)
                    except json.JSONDecodeError:
                        continue
                else:
                    payload = raw_payload
                if not isinstance(payload, dict):
                    continue
                nested_job_id = (
                    payload.get("kwargs", {})
                    .get("prompt", {})
                    .get("job_id")
                )
                if str(nested_job_id) == str(job_id):
                    prompt_messages = (
                        payload.get("kwargs", {})
                        .get("prompt", {})
                        .get("messages", [])
                    )
                    text = None
                    if prompt_messages and isinstance(prompt_messages, list):
                        first_msg = prompt_messages[0]
                        if isinstance(first_msg, dict):
                            text = first_msg.get("content")
                    return {
                        "job_id": nested_job_id,
                        "text": text,
                        "position": position + index
                    }
            position += len(messages)
            if len(messages) < batch_size:
                break
        raise ValueError(f"Message with job_id={job_id} not found in queue {queue_name}")

