"""Unit‑ and integration‑tests for :pyclass:`RabbitMQQueue`.

Highlights
~~~~~~~~~~
* **Mock section** – fast tests with a stubbed ``pika`` backend (no broker).
* **Integration section** – real RabbitMQ behind ``localhost:5672`` using the
  provided fixture.  A pre‑flight connection probe and ``pytest.skip`` avoid the
  hang when the broker is unavailable.  ``pytest.mark.timeout`` keeps the test
  from blocking >15 s even if something goes wrong.
"""
import os
import threading
import uuid
from time import sleep
import pika
import time
from types import SimpleNamespace
import pytest
from protollm_api.object_interface.message_queue.rabbitmq_adapter import RabbitMQQueue
from protollm_api.object_interface.message_queue.base import ReceivedMessage

# ---------------------------------------------------------------------------
#                               Mock‑based tests
# ---------------------------------------------------------------------------


class _FakeChannel:  # noqa: WPS110 – internal helper
    """Minimal stub replicating the bits of ``pika.channel.Channel`` we need."""

    def __init__(self) -> None:  # noqa: D401
        self.declare_calls: list[dict] = []
        self.publish_calls: list[dict] = []
        self.basic_get_result: tuple | None = None
        self.is_open = True

    # ---- queue_declare ----------------------------------------------------
    def queue_declare(self, **kwargs):  # noqa: D401
        self.declare_calls.append(kwargs)

    # ---- basic_publish ----------------------------------------------------
    def basic_publish(self, *, exchange, routing_key, body, properties, **kwargs):  # noqa: D401, WPS211
        self.publish_calls.append(
            {
                "exchange": exchange,
                "routing_key": routing_key,
                "body": body,
                "properties": properties,
            },
        )

    # ---- basic_get --------------------------------------------------------
    def basic_get(self, *, queue, auto_ack):  # noqa: D401, WPS110
        return self.basic_get_result  # type: ignore[return-value]

    # ---- misc helpers -----------------------------------------------------
    def basic_ack(self, delivery_tag):  # noqa: D401, N802
        self._acked = delivery_tag  # noqa: WPS437 – test helper

    def basic_nack(self, delivery_tag, requeue):  # noqa: D401, N802
        self._nacked = (delivery_tag, requeue)  # noqa: WPS437 – test helper

    def basic_qos(self, prefetch_count):  # noqa: D401, N802
        self.prefetch = prefetch_count  # noqa: WPS437 – test helper

    def basic_consume(self, **kwargs):  # noqa: D401, N802
        return "ctag"

    def start_consuming(self):  # noqa: D401
        pass

    def close(self):  # noqa: D401
        self.is_open = False


class _FakeConnection:  # noqa: WPS110 – internal helper
    """Stub for ``pika.BlockingConnection`` used in unit tests."""

    def __init__(self, params):  # noqa: D401, N803 – match pika signature
        self.params = params
        self._channel = _FakeChannel()
        self.is_open = True

    def channel(self):  # noqa: D401
        return self._channel

    def close(self):  # noqa: D401
        self.is_open = False


class _DummyProps(SimpleNamespace):  # noqa: WPS110 – internal helper
    """Tiny replacement for ``pika.BasicProperties``."""


@pytest.fixture(autouse=True)
def _patch_pika(monkeypatch, request):  # noqa: D401
    """Мокает *pika* только для юнит-тестов.

    Когда тест помечен маркером ``integration``, патч **не** применяется, чтобы
    использовать реальный RabbitMQ.  Это устраняет зависание ``test_priority_ordering_rabbitmq``
    при попытке подключиться к брокеру через подменённый stub.
    """

    if request.node.get_closest_marker("integration"):
        # Вернём управление тесту без патча
        yield
        return

    # ----------------------- применяем подмену ---------------------------
    fake_connection = _FakeConnection  # noqa: WPS110 – alias for brevity
    fake_props = _DummyProps

    target = "protollm_api.object_interface.message_queue.rabbitmq_adapter"
    monkeypatch.setattr(f"{target}.BlockingConnection", fake_connection)
    monkeypatch.setattr(f"{target}.BasicProperties", fake_props)

    yield(monkeypatch)


def test_declare_queue_sends_priority():  # noqa: D401
    mq = RabbitMQQueue(host="stub")
    mq.connect()
    mq.declare_queue("tasks", max_priority=7)
    fake_channel = mq._channel  # type: ignore[attr-defined]
    assert fake_channel.declare_calls, "queue_declare should be triggered"
    kwargs = fake_channel.declare_calls[0]
    assert kwargs["arguments"] == {"x-max-priority": 7}


def test_publish_passes_priority():  # noqa: D401
    mq = RabbitMQQueue(host="stub")
    mq.connect()
    mq.publish("tasks", {"content": "hello"}, priority=4)
    fake_channel = mq._channel  # type: ignore[attr-defined]
    call = fake_channel.publish_calls[0]
    assert call["properties"].priority == 4  # type: ignore[attr-defined]
    assert call["body"] == '{"content": "hello"}'


def test_get_wraps_received_message():  # noqa: D401
    mq = RabbitMQQueue(host="stub")
    mq.connect()
    fake_channel: _FakeChannel = mq._channel  # type: ignore[assignment,attr-defined]
    # craft fake return
    method = SimpleNamespace(delivery_tag=123, routing_key="tasks")
    props = _DummyProps(headers={"k": "v"}, priority=6)
    fake_channel.basic_get_result = (method, props, b"payload")

    msg = mq.get("tasks")
    assert isinstance(msg, ReceivedMessage)
    assert msg.priority == 6
    assert msg.body == b"payload"
    assert msg.headers == {"k": "v"}
    assert msg.delivery_tag == 123

# ---------------------------------------------------------------------------
#                        Integration tests (real RabbitMQ)
# ---------------------------------------------------------------------------
@pytest.fixture
def rabbitmq_connection_params():
    """Фикстура с параметрами подключения к RabbitMQ с поддержкой переменных окружения."""
    return {
        "host": os.getenv("TEST_RABBITMQ_HOST", "localhost"),
        "port": int(os.getenv("TEST_RABBITMQ_PORT", "5672")),
        "login": os.getenv("TEST_RABBITMQ_LOGIN", "admin"),
        "password": os.getenv("TEST_RABBITMQ_PASSWORD", "admin"),
    }

@pytest.mark.integration
@pytest.mark.timeout(15)
def test_priority_ordering_rabbitmq(rabbitmq_connection_params):  # noqa: D401
    """Ensure high‑priority messages are delivered before low‑priority ones."""

    _verify_rabbitmq_available(rabbitmq_connection_params)

    params = _build_connection_params(rabbitmq_connection_params)

    queue_name = f"pytest_{uuid.uuid4().hex}"

    mq = RabbitMQQueue(**params)
    with mq:
        mq.declare_queue(queue_name, max_priority=10, auto_delete=True)
        mq.publish(queue_name, {"content": "low"}, priority=1)
        mq.publish(queue_name, {"content": "high"}, priority=9)

        first = mq.get(queue_name, auto_ack=True)
        second = mq.get(queue_name, auto_ack=True)

        assert first is not None and second is not None, "Messages not received"
        assert first.body == b'{"content": "high"}'
        assert second.body == b'{"content": "low"}'


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_consume(rabbitmq_connection_params):
    """Test message re-queue on nack."""
    _verify_rabbitmq_available(rabbitmq_connection_params)

    queue_name = f"pytest_nack_{uuid.uuid4().hex}"
    params = _build_connection_params(rabbitmq_connection_params)
    delivery_counts = {}
    processed_event = threading.Event()

    mq = RabbitMQQueue(**params)
    with mq:
        mq.declare_queue(queue_name, auto_delete=True)

        test_data = {"test": "nack_test"}
        mq.publish(queue_name, test_data)

        delivery_counts = 0

        def message_handler(msg: ReceivedMessage) -> None:
            nonlocal delivery_counts
            delivery_counts += 1
            if delivery_counts == 1:
                raise Exception("Simulated processing error")
            else:
                processed_event.set()

        mq.consume(queue_name, message_handler, auto_ack=False)

        assert processed_event.wait(timeout=100), "Message was not requeued and reprocessed"

        assert delivery_counts == 2

        mq.stop_consuming()

@pytest.mark.integration
@pytest.mark.timeout(15)
def test_ack_removes_message(rabbitmq_connection_params):
    """Test that ack removes the message from the queue."""
    _verify_rabbitmq_available(rabbitmq_connection_params)

    queue_name = f"pytest_ack_{uuid.uuid4().hex}"
    params = _build_connection_params(rabbitmq_connection_params)

    mq = RabbitMQQueue(**params)
    with mq:
        mq.declare_queue(queue_name, auto_delete=True)
        test_payload = {"test": "ack_test"}
        mq.publish(queue_name, test_payload)
        processed_event = threading.Event()

        def message_handler(msg: ReceivedMessage):
            processed_event.set()

        mq.consume(queue_name, message_handler, auto_ack=False)

        assert processed_event.wait(timeout=5), "Message not processed"
        time.sleep(5)
        message = mq.get_simple(queue_name)
        assert message is None
        mq.stop_consuming()


@pytest.mark.integration
@pytest.mark.timeout(15)
def test_nack_requeues_message(rabbitmq_connection_params):
    """Test that nack with requeue=True returns message to queue."""
    queue_name = f"test_nack_{uuid.uuid4().hex}"
    _verify_rabbitmq_available(rabbitmq_connection_params)
    params = _build_connection_params(rabbitmq_connection_params)

    mq = RabbitMQQueue(**params)
    with mq:
        mq.declare_queue(queue_name, auto_delete=False)

        test_payload = {"test": "nack_test"}
        mq.publish(queue_name, test_payload)

        def message_handler(msg: ReceivedMessage):
            raise RuntimeError("Simulated processing error")

        mq.consume(queue_name, message_handler, auto_ack=False)
        sleep(1)
        mq.stop_consuming()

        mq.connect()
        remaining_message = mq.get_simple(queue_name)
        assert remaining_message.body == b'{"test": "nack_test"}', "Message removed after final nack"
        mq.delete_queue(queue_name)


# Helpers remain the same with minor improvements
def _verify_rabbitmq_available(params):
    try:
        creds = pika.PlainCredentials(params["login"], params["password"])
        conn = pika.BlockingConnection(
            pika.ConnectionParameters(
                host=params["host"],
                port=params["port"],
                credentials=creds,
                connection_attempts=1,
                blocked_connection_timeout=3,
                socket_timeout=3,
            )
        )
        conn.close()
    except Exception as e:
        pytest.skip(f"RabbitMQ unavailable: {str(e)}")


def _build_connection_params(params):
    return {
        "host": params["host"],
        "port": params["port"],
        "username": params["login"],
        "password": params["password"],
        "blocked_connection_timeout": 3,
        "heartbeat": 0,
    }


def _wait_for_condition(condition, timeout=5, interval=0.1):
    start = time.time()
    while time.time() - start < timeout:
        if condition():
            return
        time.sleep(interval)
    pytest.fail("Condition not met within timeout")

