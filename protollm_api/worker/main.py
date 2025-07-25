from protollm_api.worker.models.fake_models import FakeModel
from protollm_api.worker.services.broker import LLMWrap
from protollm_api.worker.config import Config

if __name__ == "__main__":
    config = Config.read_from_env()
    llm_model = FakeModel()
    # llm_model = OpenAPILLM(model_url="https://api.vsegpt.ru/v1",
    #                        token="sk-or-vv-23fb2234f267c0947760d5e4e1a84c08e2ffb63e9e2d2731e0b07da50239c6cd",
    #                        default_model="openai/gpt-4o-2024-08-06",)
    llm_wrap = LLMWrap(llm_model=llm_model,
                       config= config)
    llm_wrap.start_connection()
