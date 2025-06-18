from protollm_api.backend.bll.services.base import BaseBLLService
from protollm_api.backend.broker import send_task, get_result, logger
from protollm_api.backend.config import Config
from protollm_api.backend.models.job_context_models import ChatCompletionModel, ChatCompletionTransactionModel, \
    PromptTypes, ResponseModel, PromptModel
from protollm_api.object_interface import RedisResultStorage, RabbitMQQueue


class GenerateService(BaseBLLService):
    def __init__(self, redis_db: RedisResultStorage, rabbitmq: RabbitMQQueue, config: Config):
        self.redis_db = redis_db
        self.rabbitmq = rabbitmq
        self.config = config

    async def get_generate(self, prompt_data: PromptModel, queue_name: str) -> ResponseModel:
        """Вся логика запроса chat_completion, тут же обрабатывает ответ и ошибки (иил бросаем новые)"""
        transaction_model = ChatCompletionTransactionModel(
            prompt=ChatCompletionModel.from_prompt_model(prompt_data),
            prompt_type=PromptTypes.CHAT_COMPLETION.value
        )
        await send_task(self.config, queue_name, transaction_model, self.rabbitmq, self.redis_db)
        logger.info(f"Task {prompt_data.job_id} was sent to LLM.")
        return await get_result(self.config, prompt_data.job_id, self.redis_db)

