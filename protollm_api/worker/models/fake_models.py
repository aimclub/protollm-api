import logging
from time import sleep

from protollm_api.backend.models.job_context_models import PromptModel, ChatCompletionModel, PromptTransactionModel, \
    ChatCompletionTransactionModel, PromptTypes

from protollm_api.worker.models.base import BaseLLM, APIlLLM

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FakeModel(APIlLLM ,BaseLLM):
    def __init__(self):
        super().__init__("http://cringe", "lol_kek")
        self.handlers = {
            PromptTypes.SINGLE_GENERATION.value: self.generate,
            PromptTypes.CHAT_COMPLETION.value: self.create_completion,
        }

    def __call__(self, transaction: PromptTransactionModel | ChatCompletionTransactionModel):
        prompt_type: PromptTypes = transaction.prompt_type
        func = self.handlers[prompt_type]
        return func(transaction.prompt, **transaction.prompt.meta.model_dump())

    def generate(
            self,
            prompt: PromptModel,
            tokens_limit=None,
            temperature=None,
            repeat_penalty=1.1,
            stop_words=None,
            **kwargs
    ):
        logger.info(f"start generated from single prompt {prompt.content} and temp {temperature}")
        return f"GOOOL :{prompt.content}"

    def create_completion(
            self,
            prompt: ChatCompletionModel,
            tokens_limit=None,
            temperature=None,
            repeat_penalty=1.1,
            stop_words=None,
            **kwargs
    ):
        if temperature == 1:
            raise RuntimeError("Simulated processing error")
        if temperature == 2:
            sleep(100)
        logger.info(f"start generated from chat completion {prompt.messages}")
        return f"GOOOL :{prompt.messages[0]}"