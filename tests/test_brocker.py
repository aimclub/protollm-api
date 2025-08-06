import json
import uuid
from dbm.dumb import error
from unittest.mock import AsyncMock, patch, MagicMock, ANY, Mock

import pytest
from protollm_api.backend.models.job_context_models import ResponseModel, ChatCompletionTransactionModel, ChatCompletionModel, \
    PromptMeta, ChatCompletionUnit, PromptTypes

from protollm_api.backend.broker import send_task, get_result
from protollm_api.object_interface.result_storage import JobStatus, JobStatusType, JobStatusError, JobStatusErrorType
from protollm_api.object_interface.result_storage.models import JobResult


@pytest.mark.asyncio
async def test_send_task(test_local_config):
    prompt = ChatCompletionModel(
        job_id=str(uuid.uuid4()),
        priority=None,
        meta=PromptMeta(),
        messages=[ChatCompletionUnit(role="user", content="test request")]
    )
    transaction = ChatCompletionTransactionModel(prompt=prompt, prompt_type=PromptTypes.CHAT_COMPLETION.value)

    mock_rabbit = MagicMock()

    mock_redis = MagicMock()

    await send_task(test_local_config, test_local_config.queue_name, transaction, mock_rabbit, mock_redis)

    mock_redis.create_job_status.assert_called_once_with(prompt.job_id, transaction.prompt, test_local_config.redis_prefix_for_status+":", "prompt:")

    mock_rabbit.publish.assert_called_once_with(test_local_config.queue_name, ANY, priority = prompt.priority)


@pytest.mark.asyncio
async def test_get_result(test_local_config):
    redis_mock = MagicMock()
    redis_mock.get_job_result = Mock(return_value = JobResult(result = "return test success"))
    redis_mock.wait_completeness = Mock(return_value =  JobStatus(status = JobStatusType.COMPLETED, is_completed = True))
    task_id = str(uuid.uuid4())

    response = await get_result(test_local_config, task_id, redis_mock)

    redis_mock.wait_completeness.assert_called_once_with(f"{test_local_config.redis_prefix_for_status}:{task_id}",
                                                         test_local_config.timeout)
    redis_mock.get_job_result.assert_called_once_with(f"{test_local_config.redis_prefix_for_answer}:{task_id}")
    assert response == ResponseModel(content="return test success")


@pytest.mark.asyncio
async def test_get_result_with_error(test_local_config):
    redis_mock = MagicMock()
    redis_mock.wait_completeness = Mock(
        return_value =  JobStatus(status = JobStatusType.ERROR,
                                  is_completed = True,
                                  error=JobStatusError(type = JobStatusErrorType.Exception, msg = "Error")))
    task_id = str(uuid.uuid4())

    response = await get_result(test_local_config, task_id, redis_mock)

    redis_mock.wait_completeness.assert_called_once_with(f"{test_local_config.redis_prefix_for_status}:{task_id}",
                                                         test_local_config.timeout)
    assert response == ResponseModel(content="Error")


@pytest.mark.asyncio
async def test_get_result_with_exception(test_local_config):
    redis_mock = MagicMock()
    redis_mock.wait_completeness = Mock(side_effect=[Exception("Redis error")])
    task_id = str(uuid.uuid4())

    response = await get_result(test_local_config, task_id, redis_mock)

    assert response == ResponseModel(content="Job waiting finish with Error:\nRedis error")
