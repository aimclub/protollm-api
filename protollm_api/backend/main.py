from fastapi import FastAPI

from protollm_api.object_interface.message_queue.rabbitmq_adapter import RabbitMQQueue
from protollm_api.backend.config import Config

from protollm_api.backend.endpoints.sync_chat import get_sync_chat_router
from protollm_api.object_interface.result_storage import RedisResultStorage

app = FastAPI()
config = Config.read_from_env()
redis_db= RedisResultStorage(redis_host= config.redis_host, redis_port= config.redis_port)
rabbitmq = RabbitMQQueue(host= config.rabbit_host, port= config.rabbit_port, username= config.rabbit_login, password= config.rabbit_password)
app.include_router(get_sync_chat_router(config, redis_db, rabbitmq))

