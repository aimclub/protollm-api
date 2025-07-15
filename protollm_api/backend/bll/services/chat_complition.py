from protollm_api.backend.bll.services.base import BaseBLLService
from protollm_api.backend.broker import send_task, get_result, logger
from protollm_api.backend.config import Config
from protollm_api.backend.models.job_context_models import ChatCompletionModel, ChatCompletionTransactionModel, \
    PromptTypes, ResponseModel, PromptModel
from protollm_api.object_interface import RedisResultStorage, RabbitMQQueue


class ChatCompletionService(BaseBLLService):
    """
    Service for handling chat completion requests and responses.

    Manages communication between the API, message queue (RabbitMQ), and result storage (Redis).

    Args:
        redis_db (RedisResultStorage): Wrapper object for interacting with Redis database.
        rabbitmq (RabbitMQQueue): Wrapper object for interacting with RabbitMQ queues.
        config (Config): Configuration object containing service settings.
    """
    def __init__(self, redis_db: RedisResultStorage, rabbitmq: RabbitMQQueue, config: Config):
        self.redis_db = redis_db
        self.rabbitmq = rabbitmq
        self.config = config

    async def get_generate(self, prompt_data: PromptModel, queue_name: str) -> ResponseModel:
        """
        Handles generation requests by converting generic prompt to chat completion format.

        Processes a generic prompt model into chat completion format, dispatches the task to workers,
        and retrieves the generated response.

        Args:
            prompt_data (PromptModel): Input prompt data model containing job details and content
            queue_name (str): Name of the RabbitMQ queue to dispatch the task to

        Returns:
            ResponseModel: Model containing the LLM response and metadata
        """
        transaction_model = ChatCompletionTransactionModel(
            prompt=ChatCompletionModel.from_prompt_model(prompt_data),
            prompt_type=PromptTypes.CHAT_COMPLETION.value
        )
        await send_task(self.config, queue_name, transaction_model, self.rabbitmq, self.redis_db)
        logger.info(f"Task {prompt_data.job_id} was sent to LLM.")
        return await get_result(self.config, prompt_data.job_id, self.redis_db)

    async def get_chat_completion(self, prompt_data: ChatCompletionModel, queue_name: str) -> ResponseModel:
        """
        Handles chat completion requests using native chat format.

        Dispatches pre-formatted chat completion prompts to workers and retrieves generated responses.

        Args:
            prompt_data (ChatCompletionModel): Formatted chat prompt with conversation history
            queue_name (str): Name of the RabbitMQ queue to dispatch the task to

        Returns:
            ResponseModel: Model containing the LLM response and metadata
        """
        transaction_model = ChatCompletionTransactionModel(
            prompt=prompt_data,
            prompt_type=PromptTypes.CHAT_COMPLETION.value
        )
        await send_task(self.config, queue_name, transaction_model, self.rabbitmq, self.redis_db)
        logger.info(f"Task {prompt_data.job_id} was sent to LLM.")
        return await get_result(self.config, prompt_data.job_id, self.redis_db)

