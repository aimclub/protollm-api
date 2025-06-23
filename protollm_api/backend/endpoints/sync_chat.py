from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from protollm_api.backend.bll.services.chat_complition import ChatCompletionService
from protollm_api.backend.bll.services.generate import GenerateService
from protollm_api.backend.broker import send_task, logger, get_result
from protollm_api.backend.config import Config
from protollm_api.backend.models.job_context_models import ResponseModel, ChatCompletionTransactionModel, PromptModel, \
    ChatCompletionModel, PromptTypes, QueuesNamesResponse, QueueInfoResponse, PeekMessagesResponse
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

    def get_generate_service(
            redis: RedisResultStorage = Depends(lambda: redis_db),
            rmq: RabbitMQQueue = Depends(lambda: rabbitmq),
            cfg: Config = Depends(lambda: config)
    ) -> GenerateService:
        return GenerateService(redis, rmq, cfg)

    @router.post('/generate', response_model=ResponseModel)
    async def generate(
            generate_service: Annotated[GenerateService, Depends(get_generate_service)],
            prompt_data: PromptModel,
            queue_name: str = config.queue_name
    ):
        return await generate_service.get_generate(prompt_data, queue_name)

    @router.post('/chat_completion', response_model=ResponseModel)
    async def chat_completion(
            chat_completion_service: Annotated[ChatCompletionService, Depends(get_chat_completion_service)],
            prompt_data: ChatCompletionModel,
            queue_name: str = config.queue_name,
    ):
        return await chat_completion_service.get_chat_completion(prompt_data, queue_name)

    @router.get("/queue_list", response_model=QueuesNamesResponse)
    def get_queue_list():
        try:
            result = rabbitmq.list_queues(timeout=5)
            return QueuesNamesResponse(queues_names=result)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/queue_info/{queue_name}", response_model=QueueInfoResponse, response_model_exclude_unset=True)
    def get_queue_info(queue_name: str):
        try:
            queue_data = rabbitmq.get_queue_info(queue_name)
            model = QueueInfoResponse(**queue_data)
            return model.dict(include=model.__fields__.keys())
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/queue_messages/{queue_name}", response_model=PeekMessagesResponse, response_model_exclude_unset=True)
    def get_queue_messages(queue_name: str, count: Optional[int] = Query(None, ge=1, le=10000)):
        try:
            if count is None:
                queue_info = rabbitmq.get_queue_info(queue_name)
                count = queue_info.get("messages", 0)
            if not count:
                return PeekMessagesResponse(messages=[])
            messages = rabbitmq.peek_queue_messages(queue_name=queue_name, count=count)
            model = PeekMessagesResponse(messages=messages)
            return model.dict(include=model.__fields__.keys())
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router
