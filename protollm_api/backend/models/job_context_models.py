from enum import Enum
from typing import Literal, Union, Optional, Any

from pydantic import BaseModel, Field


class PromptTypes(Enum):
    SINGLE_GENERATION: str = "single_generation"
    CHAT_COMPLETION: str = "chat_completion"


class PromptMeta(BaseModel):
    temperature: float | None = 0.2
    tokens_limit: int | None = 8096
    stop_words: list[str] | None = None
    model: str | None = Field(default=None, examples=[None])


class PromptModel(BaseModel):
    job_id: str
    priority: int | None = Field(default=None, examples=[None])
    meta: PromptMeta
    content: str


class ChatCompletionUnit(BaseModel):
    """A model for element of chat completion"""
    role: str
    content: str


class ChatCompletionModel(BaseModel):
    """A model for chat completion order"""
    job_id: str
    priority: int | None = Field(default=None, examples=[None])
    source: str = "local"
    meta: PromptMeta
    messages: list[ChatCompletionUnit]

    @classmethod
    def from_prompt_model(cls, prompt_model: PromptModel) -> 'ChatCompletionModel':
        # Создаем первое сообщение из содержимого PromptModel
        initial_message = ChatCompletionUnit(
            role="user",  # Или другой подходящий role
            content=prompt_model.content
        )
        # Возвращаем новый экземпляр ChatCompletionModel
        return cls(
            job_id=prompt_model.job_id,
            priority=prompt_model.priority,
            meta=prompt_model.meta,
            messages=[initial_message]
        )


class PromptTransactionModel(BaseModel):
    prompt: PromptModel
    prompt_type: Literal[PromptTypes.SINGLE_GENERATION.value]


class ChatCompletionTransactionModel(BaseModel):
    prompt: ChatCompletionModel
    prompt_type: Literal[PromptTypes.CHAT_COMPLETION.value]


class PromptWrapper(BaseModel):
    prompt: Union[PromptTransactionModel, ChatCompletionTransactionModel] = Field(..., discriminator='prompt_type')


class ResponseModel(BaseModel):
    content: str


class LLMResponse(BaseModel):
    job_id: str
    text: str


class TextEmbedderRequest(BaseModel):
    job_id: str
    inputs: str
    truncate: bool


class ToEmbed(BaseModel):
    inputs: str
    truncate: bool

class TextEmbedderResponse(BaseModel):
    embeddings: list[float]

class QueuesNamesResponse(BaseModel):
    queues_names: list[str]
    error: Optional[str] = Field(default=None, description="Error message, if any")

class QueueInfoResponse(BaseModel):
    name: str = Field(..., description="Queue name")
    vhost: str = Field(..., description="Virtual host to which the queue belongs")
    durable: bool = Field(..., description="Whether the queue survives broker restarts")
    auto_delete: bool = Field(..., description="Whether the queue is automatically deleted when unused")
    exclusive: bool = Field(..., description="If true, the queue is exclusive to one connection only")
    messages: int = Field(..., description="Total number of messages (ready + unacknowledged)")
    messages_ready: int = Field(..., description="Messages available for delivery to consumers")
    messages_unacknowledged: int = Field(..., description="Messages delivered but not yet acknowledged")
    consumers: int = Field(..., description="Number of consumers currently subscribed to the queue")
    state: str = Field(..., description="Current state of the queue (e.g., running)")
    memory: Optional[int] = Field(None, description="Memory used by the queue (in bytes)")
    consumer_utilisation: Optional[float] = Field(None, description="Fraction of time the queue is being actively consumed")
    idle_since: Optional[str] = Field(None, description="Timestamp when the queue became idle (ISO format)")
    class Config:
        extra = "allow"

class SimplifiedMessageProperties(BaseModel):
    content_type: Optional[str] = Field(None, description="MIME type of the message payload")
    message_id: Optional[str] = Field(None, description="Optional identifier of the message")
    timestamp: Optional[int] = Field(None, description="UNIX timestamp when the message was published")

class SimplifiedRabbitMQMessage(BaseModel):
    payload: Any = Field(..., description="Raw content of the message")
    redelivered: bool = Field(..., description="True if the message has been previously delivered but not acknowledged")
    exchange: str = Field(..., description="Exchange through which the message was published")
    routing_key: str = Field(..., description="Routing key used to deliver the message")
    properties: SimplifiedMessageProperties = Field(..., description="Selected AMQP properties of the message")

class PeekMessagesResponse(BaseModel):
    messages: list[SimplifiedRabbitMQMessage] = Field(..., description="List of peeked messages")