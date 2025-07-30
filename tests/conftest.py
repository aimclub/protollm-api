import pytest
import redis
from protollm_api.backend.config import Config
from protollm_api.object_interface import RedisResultStorage


@pytest.fixture(scope="module")
def test_local_config():
    return Config()


@pytest.fixture(scope="module")
def test_real_config():
    return Config.read_from_env()


@pytest.fixture(scope="module")
def redis_client(test_local_config):
    """Fresh RedisResultStorage for each test."""
    pool = redis.ConnectionPool(host=test_local_config.redis_host, port=test_local_config.redis_port, db=0)
    return redis.Redis(connection_pool=pool)

@pytest.fixture(scope="module")
def redis_storage(redis_client):
    """Fresh RedisResultStorage for each test."""
    return RedisResultStorage(redis_client=redis_client)