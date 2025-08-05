import logging
from lib2to3.fixes.fix_input import context

from celery.bin.result import result
from click import prompt

from protollm_api.object_interface.message_queue.rabbitmq_adapter import RabbitMQQueue
from protollm_api.backend.config import Config
from protollm_api.backend.models.job_context_models import (
    ResponseModel, ChatCompletionTransactionModel, PromptTransactionModel)
from protollm_api.object_interface.result_storage import RedisResultStorage, JobStatusType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def send_task(config: Config,
                    queue_name: str,
                    transaction: ChatCompletionTransactionModel,
                    rabbitmq: RabbitMQQueue,
                    redis_db: RedisResultStorage,
                    task_type='generate'):
    """
    Sends a task to the RabbitMQ queue.

    Args:
        config (Config): Configuration object containing RabbitMQ connection details.
        queue_name (str): Name of the RabbitMQ queue where the task will be published.
        transaction (PromptTransactionModel | ChatCompletionTransactionModel): Transaction data to be sent.
        rabbitmq (RabbitMQQueue): Rabbit wrapper object to interact with the Rabbit queue.
        redis_db (RedisResultStorage): Redis wrapper object to interact with the Redis database.
        task_type (str, optional): The type of task to be executed (default is 'generate').

    Raises:
        Exception: If there is an error during the connection or message publishing process.
    """
    if transaction.prompt.priority is None:
        transaction.prompt.priority = config.base_priority

    task = {
        "type": "task",
        "task": task_type,
        "args": [],
        "kwargs": transaction.model_dump(),
        "id": transaction.prompt.job_id,
        "retries": 0,
        "eta": None
    }

    redis_db.create_job_status(task['id'],
                               transaction.prompt,
                               f"{config.redis_prefix_for_status}:",
                               f"prompt:")

    with rabbitmq:
        rabbitmq.publish(
            queue_name,
            task,
            priority= transaction.prompt.priority
        )



async def get_result(config: Config, task_id: str, redis_db: RedisResultStorage) -> ResponseModel:
    """
    Retrieves the result of a task from Redis.

    Args:
        config (Config): Configuration object containing Redis connection details.
        task_id (str): ID of the task whose result is to be retrieved.
        redis_db (RedisResultStorage): Redis wrapper object to interact with the Redis database.

    Returns:
        ResponseModel: Parsed response model containing the result.

    Raises:
        Exception: If the result is not found within the timeout period or other errors occur.
    """
    logger.info(f"Trying to get data from Redis")
    logger.info(f"Redis key: {config.redis_prefix_for_status}:{task_id}")
    try:
        job_status = redis_db.wait_completeness(f"{config.redis_prefix_for_status}:{task_id}")
    except TimeoutError as te:
        return ResponseModel(content=f"Job dont finish in fixed time with Error:\n{str(te)}")
    except Exception as e:
        return ResponseModel(content=f"Job waiting finish with Error:\n{str(e)}")
    if job_status.status == JobStatusType.COMPLETED:
        job_result = redis_db.get_job_result(f"{config.redis_prefix_for_answer}:{task_id}")
        return ResponseModel(content= job_result.result)
    if job_status.status == JobStatusType.ERROR:
        return ResponseModel(content=str(job_status.error.msg))
    return ResponseModel(content="Somthing goes wrong and job do not finished")
