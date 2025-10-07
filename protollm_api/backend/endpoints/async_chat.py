from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from protollm_api.backend.bll.services.async_chat_complition import AsyncChatCompletionService
from protollm_api.backend.exeption import JobNotFoundError
from protollm_api.backend.models.job_context_models import ResponseModel, PromptModel, ChatCompletionModel, \
    AsyncResponseModel
from protollm_api.object_interface.message_queue.rabbitmq_adapter import RabbitMQQueue
from protollm_api.backend.config import Config
from protollm_api.object_interface.result_storage import RedisResultStorage


def get_async_chat_router(config: Config, redis_db: RedisResultStorage, rabbitmq: RabbitMQQueue) -> APIRouter:
    router = APIRouter(
        prefix="",
        tags=["root"],
        responses={404: {"description": "Not found"}},
    )

    def get_async_chat_completion_service(
            redis: RedisResultStorage = Depends(lambda: redis_db),
            rmq: RabbitMQQueue = Depends(lambda: rabbitmq),
            cfg: Config = Depends(lambda: config)
    ) -> AsyncChatCompletionService:
        return AsyncChatCompletionService(redis, rmq, cfg)

    @router.post('/generate', response_model=ResponseModel)
    async def generate(
            async_chat_completion_service: Annotated[
                AsyncChatCompletionService, Depends(get_async_chat_completion_service)],
            prompt_data: PromptModel,
            queue_name: str = config.queue_name
    ):
        return await async_chat_completion_service.get_generate(prompt_data, queue_name)

    @router.post('/chat_completion', response_model=ResponseModel)
    async def chat_completion(
            async_chat_completion_service: Annotated[
                AsyncChatCompletionService, Depends(get_async_chat_completion_service)],
            prompt_data: ChatCompletionModel,
            queue_name: str = config.queue_name,
    ):
        return await async_chat_completion_service.get_chat_completion(prompt_data, queue_name)

    @router.post('/check_status', response_model=AsyncResponseModel)
    async def check_status(
            async_chat_completion_service: Annotated[
                AsyncChatCompletionService, Depends(get_async_chat_completion_service)],
            job_id: str,
    ):
        try:
            result = await async_chat_completion_service.get_status(job_id)
            return result
        except Exception as e:
            if e.__class__ is JobNotFoundError:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Status for job: {job_id} not found"
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Something goes wrong: {str(e)}"
            )

    return router