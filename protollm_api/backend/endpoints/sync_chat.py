from fastapi import APIRouter
from protollm_api.backend.broker import send_task, logger, get_result
from protollm_api.backend.config import Config
from protollm_api.backend.models.job_context_models import ResponseModel, ChatCompletionTransactionModel, PromptModel, \
    ChatCompletionModel, PromptTypes
from protollm_api.object_interface.message_queue.rabbitmq_adapter import RabbitMQQueue
from protollm_api.object_interface.result_storage import RedisResultStorage


def get_sync_chat_router(config: Config, redis_db: RedisResultStorage, rabbitmq: RabbitMQQueue) -> APIRouter:
    router = APIRouter(
        prefix="",
        tags=["root"],
        responses={404: {"description": "Not found"}},
    )

    @router.post('/generate', response_model=ResponseModel)
    async def generate(prompt_data: PromptModel, queue_name: str = config.queue_name):
        transaction_model = ChatCompletionTransactionModel(
            prompt=ChatCompletionModel.from_prompt_model(prompt_data),
            prompt_type=PromptTypes.CHAT_COMPLETION.value
        )
        await send_task(config, queue_name, transaction_model, rabbitmq, redis_db)
        result = await get_result(config, prompt_data.job_id, redis_db)
        logger.info(f"Task {prompt_data.job_id} was sent to LLM.")
        return result

    @router.post('/chat_completion', response_model=ResponseModel)
    async def chat_completion(
            prompt_data: ChatCompletionModel,
            #chat_completion_service: Annotated[ChatCompletionService, Depends()], # chat_completion_service: ChatCompletionService = Depends()
            queue_name: str = config.queue_name,
    ):
        transaction_model = ChatCompletionTransactionModel(
            prompt=prompt_data,
            prompt_type=PromptTypes.CHAT_COMPLETION.value
        )
        await send_task(config, queue_name, transaction_model, rabbitmq, redis_db)
        logger.info(f"Task {prompt_data.job_id} was sent to LLM.")
        return await get_result(config, prompt_data.job_id, redis_db)

    return router
