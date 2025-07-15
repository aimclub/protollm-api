from typing import Annotated

from fastapi import APIRouter, Depends

from protollm_api.backend.bll.services.chat_complition import ChatCompletionService
from protollm_api.backend.config import Config
from protollm_api.backend.models.job_context_models import ResponseModel, PromptModel, ChatCompletionModel
from protollm_api.object_interface.message_queue.rabbitmq_adapter import RabbitMQQueue
from protollm_api.object_interface.result_storage import RedisResultStorage


def get_sync_chat_router(config: Config, redis_db: RedisResultStorage, rabbitmq: RabbitMQQueue) -> APIRouter:
    router = APIRouter(
        prefix="",
        tags=["root"],
        responses={404: {"description": "Not found"}},
    )

    def get_chat_completion_service(
            redis: RedisResultStorage = Depends(lambda: redis_db),
            rmq: RabbitMQQueue = Depends(lambda: rabbitmq),
            cfg: Config = Depends(lambda: config)
    ) -> ChatCompletionService:
        return ChatCompletionService(redis, rmq, cfg)

    @router.post('/generate', response_model=ResponseModel)
    async def generate(
            chat_completion_service: Annotated[ChatCompletionService, Depends(get_chat_completion_service)],
            prompt_data: PromptModel,
            queue_name: str = config.queue_name
    ):
        return await chat_completion_service.get_generate(prompt_data, queue_name)

    @router.post('/chat_completion', response_model=ResponseModel)
    async def chat_completion(
            chat_completion_service: Annotated[ChatCompletionService, Depends(get_chat_completion_service)],
            prompt_data: ChatCompletionModel,
            queue_name: str = config.queue_name,
    ):
        return await chat_completion_service.get_chat_completion(prompt_data, queue_name)


    return router
