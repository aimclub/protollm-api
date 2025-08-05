import threading
import time
import uuid

import pytest
import redis

from protollm_api.object_interface.result_storage.models import (
    JobStatusError,
    JobStatusErrorType,
    JobStatusType,
)
from protollm_api.object_interface.result_storage import RedisResultStorage

# --------------------------------------------------------------------------- #
#  Fixtures                                                                    #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
#  Basic operations                                                            #
# --------------------------------------------------------------------------- #

def test_create_and_get(redis_storage, prompt, test_local_config):
    job_id = f"job-{uuid.uuid4()}"
    redis_storage.create_job_status(job_id, prompt, test_local_config.redis_prefix_for_status+":")

    status = redis_storage.get_job_status(test_local_config.redis_prefix_for_status+":"+job_id)
    assert status.status is JobStatusType.PENDING
    assert status.status_message == "Job is created"
    assert status.is_completed is False


@pytest.mark.parametrize(
    "new_status, msg",
    [
        (JobStatusType.IN_PROGRESS, "working"),
    ],
)
def test_update_job_status(redis_storage, new_status, msg, prompt, test_local_config):
    job_id = f"job-{uuid.uuid4()}"
    redis_storage.create_job_status(job_id, prompt, test_local_config.redis_prefix_for_status+":")

    redis_storage.update_job_status(test_local_config.redis_prefix_for_status+":"+job_id, new_status, msg)
    status = redis_storage.get_job_status(test_local_config.redis_prefix_for_status+":"+job_id)

    assert status.status is new_status
    assert status.status_message == msg
    assert status.is_completed is False


def test_complete_job_success(redis_storage, prompt, test_local_config):
    job_id = f"job-{uuid.uuid4()}"
    redis_storage.create_job_status(job_id, prompt, test_local_config.redis_prefix_for_status+":", test_local_config.redis_prefix_for_answer+":")

    redis_storage.complete_job(job_id,
                               result='{"answer":42}',
                               status_message="done",
                               status_prefix=test_local_config.redis_prefix_for_status+":",
                               result_prefix=test_local_config.redis_prefix_for_answer+":")

    status = redis_storage.get_job_status(test_local_config.redis_prefix_for_status+":"+job_id)
    result = redis_storage.get_job_result(test_local_config.redis_prefix_for_answer+":"+job_id)
    assert status.status is JobStatusType.COMPLETED
    assert result.result == '{"answer":42}'
    assert status.is_completed is True
    assert status.error is None


def test_complete_job_error(redis_storage, prompt, test_local_config):
    job_id = f"job-{uuid.uuid4()}"
    redis_storage.create_job_status(job_id, prompt, test_local_config.redis_prefix_for_status+":")

    err = JobStatusError(type=JobStatusErrorType.ValidationError, msg="boom")
    redis_storage.complete_job(job_id, error=err, status_message="failed")

    status = redis_storage.get_job_status(job_id)
    assert status.status is JobStatusType.ERROR
    assert status.error == err
    assert status.is_completed is True


def test_delete_job_status(redis_storage, redis_client, prompt, test_local_config):
    job_id = f"job-{uuid.uuid4()}"
    redis_storage.create_job_status(job_id, prompt, test_local_config.redis_prefix_for_status+":")

    redis_storage.delete_job_status(test_local_config.redis_prefix_for_status+":"+job_id)
    assert redis_client.get(test_local_config.redis_prefix_for_status+":"+job_id) is None


# --------------------------------------------------------------------------- #
#  Pub/Sub behaviour                                                           #
# --------------------------------------------------------------------------- #

def test_subscribe_receives_updates(redis_storage, prompt, test_local_config):
    job_id = f"job-{uuid.uuid4()}"
    redis_storage.create_job_status(job_id, prompt, test_local_config.redis_prefix_for_status+":", test_local_config.redis_prefix_for_answer+":")

    generator = redis_storage.subscribe(test_local_config.redis_prefix_for_status+":"+job_id, timeout=5)

    def updater():
        time.sleep(0.2)
        redis_storage.update_job_status(test_local_config.redis_prefix_for_status+":"+job_id, JobStatusType.IN_PROGRESS, "running")
        time.sleep(0.2)
        redis_storage.complete_job(job_id,
                                   result="{}",
                                   status_prefix= test_local_config.redis_prefix_for_status+":",
                                   result_prefix= test_local_config.redis_prefix_for_answer+":")

    thread = threading.Thread(target=updater)
    thread.start()

    updates = list(generator)      # stops automatically on completion
    thread.join()

    assert len(updates) == 2
    assert updates[0].status is JobStatusType.IN_PROGRESS
    assert updates[1].status is JobStatusType.COMPLETED
    assert updates[1].is_completed is True


def test_wait_completeness_success(redis_storage, prompt, test_local_config):
    job_id = f"job-{uuid.uuid4()}"
    redis_storage.create_job_status(job_id, prompt, test_local_config.redis_prefix_for_status+":", test_local_config.redis_prefix_for_answer+":")

    def completer():
        time.sleep(0.3)
        redis_storage.complete_job(job_id,
                                   result='{"ok":1}',
                                   status_prefix= test_local_config.redis_prefix_for_status+":",
                                   result_prefix= test_local_config.redis_prefix_for_answer+":")

    thread = threading.Thread(target=completer)
    thread.start()

    final_status = redis_storage.wait_completeness(test_local_config.redis_prefix_for_status+":"+job_id, timeout=5)
    thread.join()

    assert final_status.status is JobStatusType.COMPLETED
    assert final_status.is_completed is True


def test_wait_completeness_timeout(redis_storage, prompt, test_local_config):
    job_id = f"job-{uuid.uuid4()}"
    redis_storage.create_job_status(job_id, prompt, test_local_config.redis_prefix_for_status+":")

    with pytest.raises(TimeoutError):
        redis_storage.wait_completeness(test_local_config.redis_prefix_for_status+":"+job_id, timeout=1)