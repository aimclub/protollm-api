from protollm_api.worker.models.open_api_llm import OpenAPILLM
from protollm_api.worker.services import LLMWrap
from protollm_api.worker.config import Config

if __name__ == "__main__":
    config = Config.read_from_env_file(".env")
    llm_model = OpenAPILLM(model_url="https://api.vsegpt.ru/v1",
                           token="sk-or-vv-8f5573fbef6a4d3dc5cbf6a6b756b313f2b2d8afa24b41ba28bcf3154c5f1178",
                           default_model="openai/gpt-4o-2024-08-06",
                           # app_tag="test_protollm_worker"
                           )
    # llm_model = VllMModel(model_path=config.model_path,
    #                       tensor_parallel_size=config.tensor_parallel_size,
    #                       gpu_memory_utilisation=config.gpu_memory_utilisation,
    #                       tokens_len=config.token_len)
    llm_wrap = LLMWrap(llm_model=llm_model,
                       config= config)
    llm_wrap.start_connection()
