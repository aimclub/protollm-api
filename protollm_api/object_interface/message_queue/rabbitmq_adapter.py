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
import threading
import time
from typing import Any, Callable, Optional

import pika
from pika import BasicProperties, BlockingConnection, ConnectionParameters, PlainCredentials

from .base import BaseMessageQueue, ReceivedMessage

log = logging.getLogger(__name__)


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
        self._active = threading.Event()
        self._consumer_tag = None
        self._consume_thread: threading.Thread | None = None

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
        self.stop_consuming()

        if not self._connection:
            return

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

    def get_simple(self, queue, auto_ack=False):
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
        return None


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
            result = self.get_simple(queue, auto_ack)
            if result:
                return result
            # No task yet
            if timeout is not None and (time.monotonic() - start) >= timeout:
                return None
            time.sleep(0.1)

    # Добавляем в класс RabbitMQQueue следующие методы:
    def consume(
            self,
            queue: str,
            callback: Callable[[ReceivedMessage], Any],
            *,
            auto_ack: bool = False,
            **kwargs: Any,
    ) -> None:
        """Start consuming messages from queue in background thread."""
        if self._active.is_set():
            raise RuntimeError("Consumer is already running")

        self.connect()
        self._active.set()

        # Создаем поток для обработки сообщений
        self._consume_thread = threading.Thread(
            target=self._consume_loop,
            args=(queue, callback, auto_ack),
            daemon=False,
            name=f"RabbitMQConsumer-{queue}",
        )
        self._consume_thread.start()

    def wait(self, timeout: float | None = None) -> None:
        """Wait for consumer to finish."""
        if self._consume_thread:
            self._consume_thread.join(timeout=timeout)

    def _consume_loop(
            self,
            queue: str,
            callback: Callable[[ReceivedMessage], Any],
            auto_ack: bool,
    ) -> None:
        """Main loop for message consumption."""
        try:
            def message_handler(ch, method, properties, body):
                msg = self._translate_message(method, properties, body)
                try:
                    callback(msg)
                    if not auto_ack:
                        self.ack(msg)  # Используем публичный метод
                except Exception as e:
                    log.exception("Message processing failed: %s", e)
                    if not auto_ack:
                        self.nack(msg)  # Используем публичный метод

            consumer_tag = self._channel.basic_consume(
                queue=queue,
                on_message_callback=message_handler,
                auto_ack=auto_ack,
            )
            self._consumer_tag = consumer_tag
            log.info("Started consuming queue '%s'", queue)

            while self._active.is_set():
                self._connection.process_data_events(time_limit=1.0)

        except Exception as e:
            log.exception("Consumer loop crashed: %s", e)
        finally:
            self.stop_consuming()

    def stop_consuming(self) -> None:
        """Stop message consumption and background thread."""
        if not self._active.is_set():
            return

        self._active.clear()

        # Отменяем подписку
        if self._channel and self._consumer_tag:
            try:
                self._channel.basic_cancel(self._consumer_tag)
                log.debug("Canceled consumer %s", self._consumer_tag)
            except Exception as e:
                log.exception("Error canceling consumer: %s", e)
            finally:
                self._consumer_tag = None

        # Ожидаем завершение потока
        if self._consume_thread and self._consume_thread.is_alive():
            self._consume_thread.join(timeout=5.0)
            if self._consume_thread.is_alive():
                log.warning("Consumer thread did not terminate gracefully")
            self._consume_thread = None

    def ack(self, message: ReceivedMessage) -> None:
        """Acknowledge the message processing."""
        if not self._channel:
            raise RuntimeError("Channel is not available")
        self._channel.basic_ack(message.delivery_tag)

    def nack(self, message: ReceivedMessage) -> None:
        """Negative acknowledge and requeue the message."""
        if not self._channel:
            raise RuntimeError("Channel is not available")
        self._channel.basic_nack(message.delivery_tag, requeue=True)