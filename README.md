# protollm-api

Contains protollm-backend and protollm-worker

# protollm-backend

This API allows interaction with a distributed LLM architecture using RabbitMQ and Redis. Requests are processed asynchronously by a worker system (LLM-core) that generates responses and saves them to Redis. The API retrieves results from Redis and sends them back to the user.

---

## Endpoints

### `/generate`
- **Method**: `POST`
- **Description**: Sends a prompt for single message generation.
- **Request Body**:
  ```json
  {
    "job_id": "string",
    "meta": {
      "temperature": 0.2,
      "tokens_limit": 8096,
      "stop_words": [
        "string"
      ],
      "model": "string"
    },
    "content": "string"
  }
  ```
  - `job_id` (string): Unique identifier for the task.
  - `meta` (object): Metadata for generation:
    - `temperature` (float): The degree of randomness in generation (default 0.2).
    - `tokens_limit` (integer): Maximum tokens for the response (default 8096).
    - `stop_words` (list of strings): Words to stop generation.
    - `model` (string): Model to use for generation.
  - `content` (string): The input text for generation.
- **Response**:
  ```json
  {
    "content": "string"
  }
  ```
  - `content` (string): The generated text.

---

### `/chat_completion`
- **Method**: `POST`
- **Description**: Sends a conversation history for chat-based completions.
- **Request Body**:
  ```json
  {
    "job_id": "string",
    "meta": {
      "temperature": 0.2,
      "tokens_limit": 8096,
      "stop_words": [
        "string"
      ],
      "model": "string"
    },
    "messages": [
      {
        "role": "string",
        "content": "string"
      }
    ]
  }
  ```
  - `job_id` (string): Unique identifier for the task.
  - `meta` (object): Metadata for chat completion:
    - `temperature` (float): The degree of randomness in responses (default 0.2).
    - `tokens_limit` (integer): Maximum tokens for the response (default 8096).
    - `stop_words` (list of strings): Words to stop the generation.
    - `model` (string): Model to use for chat completion.
  - `messages` (list of objects): Conversation history:
    - `role` (string): Role of the message sender (`"user"`, `"assistant"`, etc.).
    - `content` (string): Message content.
- **Response**:
  ```json
  {
    "content": "string"
  }
  ```
  - `content` (string): The generated response.

---

## Environment Variables

These variables must be configured and synchronized with the LLM-core system:

### RabbitMQ Configuration
- `RABBIT_MQ_HOST`: RabbitMQ server hostname or IP.
- `RABBIT_MQ_PORT`: RabbitMQ server port.
- `RABBIT_MQ_LOGIN`: RabbitMQ login username.
- `RABBIT_MQ_PASSWORD`: RabbitMQ login password.
- `QUEUE_NAME`: Name of the RabbitMQ queue to process tasks.

### Redis Configuration
- `REDIS_HOST`: Redis server hostname or IP.
- `REDIS_PORT`: Redis server port.
- `REDIS_PREFIX`: Key prefix for task results in Redis.

### Internal LLM-core Configuration
- `INNER_LLM_URL`: URL for the LLM-core worker service.

### Example `.env` File
```env
# API
CELERY_BROKER_URL=amqp://admin:admin@127.0.0.1:5672/
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
REDIS_HOST=redis
REDIS_PORT=6379
RABBIT_MQ_HOST=rabbitmq
RABBIT_MQ_PORT=5672
RABBIT_MQ_LOGIN=admin
RABBIT_MQ_PASSWORD=admin
WEB_RABBIT_MQ=15672
API_PORT=6672

# RabbitMQ
RABBITMQ_DEFAULT_USER=admin
RABBITMQ_DEFAULT_PASS=admin
```

---

## System Architecture

Below is the architecture diagram for the interaction between API, RabbitMQ, LLM-core, and Redis:

```plaintext
+-------------------+       +-----------------+       +----------------+       +-------------------+
|                   |       |                 |       |                |       |                   |
|       API         +------>+    RabbitMQ     +------>+    LLM-core    +------>+      Redis         |
|                   |       |                 |       |                |       |                   |
+-------------------+       +-----------------+       +----------------+       +-------------------+
        ^                             ^                                ^
        |                             |                                |
        |      Requests are queued    |    Worker retrieves tasks     | Results are stored in Redis
        |      Results are polled     |                                |
        +-----------------------------+--------------------------------+
```

### Flow
1. **API**:
   - Receives requests via endpoints (`/generate`, `/chat_completion`).
   - Publishes tasks to RabbitMQ.
   - Polls Redis for results based on task IDs.

2. **RabbitMQ**:
   - Acts as a queue for task distribution.
   - LLM-core workers subscribe to queues to process tasks.

3. **LLM-core**:
   - Retrieves tasks from RabbitMQ.
   - Processes prompts or chat completions using LLM models.
   - Stores results in Redis.

4. **Redis**:
   - Acts as the result storage.
   - API retrieves results from Redis when tasks are completed.

---

## Usage

### Running the API
1. Configure environment variables in the `.env` file.
2. Start the API using:
```python
app = FastAPI()

config = Config.read_from_env()

app.include_router(get_router(config))
```
### Running the API Locally (without Docker)
To run the API locally using Uvicorn, use the following command:

```sh
uvicorn protollm_api.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Or use this main file:
```python
app = FastAPI()

config = Config.read_from_env()

app.include_router(get_router(config))
    
if __name__ == "__main__":
    uvicorn.run("protollm_api.backend.main:app", host="127.0.0.1", port=8000, reload=True)
```
### Example Request
#### Generate
```bash
curl -X POST "http://localhost:8000/generate" -H "Content-Type: application/json" -d '{
  "job_id": "12345",
  "meta": {
    "temperature": 0.5,
    "tokens_limit": 1000,
    "stop_words": ["stop"],
    "model": "gpt-model"
  },
  "content": "What is AI?"
}'
```

#### Chat Completion
```bash
curl -X POST "http://localhost:8000/chat_completion" -H "Content-Type: application/json" -d '{
  "job_id": "12345",
  "meta": {
    "temperature": 0.5,
    "tokens_limit": 1000,
    "stop_words": ["stop"],
    "model": "gpt-model"
  },
  "messages": [
    {"role": "user", "content": "What is AI?"},
    {"role": "assistant", "content": "Artificial Intelligence is..."}
  ]
}'
```

---

## Notes
- Ensure that `RABBIT_MQ_HOST`, `RABBIT_MQ_PORT`, `REDIS_HOST`, and other variables are synchronized between the API and LLM-core containers.
- The system supports distributed scaling by adding more LLM-core workers to the RabbitMQ queue.

# protollm-worker

## Introduction

This repository provides a template for deploying large language models (LLMs) using Docker Compose. The setup is designed to integrate multiple models with GPU support, Redis for data storage, and RabbitMQ for task queuing and processing. The provided `main.py` script demonstrates how to initialize and run a connection to process tasks using any model that inherits from the base model class.

---

## Table of Contents

1. [Docker Compose Setup](#docker-compose-setup)
   - [Adding Multiple Models](#adding-multiple-models)
2. [Main Script Overview](#main-script-overview)
   - [Using Custom Models](#using-custom-models)
3. [Environment Variable Configuration](#environment-variable-configuration)
   - [Synchronization with API](#synchronization-with-api)

---

## Docker Compose Setup

The provided `docker-compose.yml` template can be used to deploy your LLM model(s). It supports GPU execution and integration with a shared network (`llm_wrap_network`).

### Example `docker-compose.yml`

```yaml
version: '3.8'

services:
  llm:
    container_name: <your_container_name>
    image: <your_image_name>:latest
    runtime: nvidia
    deploy:
      resources:
        limits:
          memory: 100G
    build:
      context: ../../protollm_api
      dockerfile: Dockerfile
    env_file: .env
    environment:
      FORCE_CMAKE: 1
    volumes:
      - <your_path_to_data_in_docker>:/data
    ports:
      - "8677:8672"
    networks:
      - llm_wrap_network
    restart: unless-stopped

networks:
  llm_wrap_network:
    name: llm_wrap_network
    driver: bridge
```

### Adding Multiple Models

You can define multiple models by duplicating the service block in `docker-compose.yml` and adjusting the relevant parameters (e.g., container name, ports, GPUs). For example:

```yaml
services:
  llm_1:
    container_name: llm_model_1
    image: llm_image:latest
    runtime: nvidia
    environment:
      MODEL_PATH: /data/model_1
      NVIDIA_VISIBLE_DEVICES: "GPU-1"
    ports:
      - "8677:8672"

  llm_2:
    container_name: llm_model_2
    image: llm_image:latest
    runtime: nvidia
    environment:
      MODEL_PATH: /data/model_2
      NVIDIA_VISIBLE_DEVICES: "GPU-2"
    ports:
      - "8678:8672"

networks:
  llm_wrap_network:
    name: llm_wrap_network
    driver: bridge
```

By assigning separate GPUs and ports, you can scale your infrastructure to serve multiple models simultaneously.

---

## Main Script Overview

The provided `main.py` script demonstrates how to initialize and run the LLM wrapper (`LLMWrap`) with a selected model. The wrapper uses RabbitMQ for task queuing and Redis for result storage.

### Key Components

1. **Model Initialization**:
   ```python
   llm_model = VllMModel(model_path=MODEL_PATH)
   ```
   - Any model inheriting from `BaseLLM` can be used here.
   - Replace `VllMModel` with your custom model class if needed.

2. **LLMWrap Initialization**:
   ```python
   llm_wrap = LLMWrap(
       llm_model=llm_model,
       redis_host=REDIS_HOST,
       redis_port=REDIS_PORT,
       queue_name=QUEUE_NAME,
       rabbit_host=RABBIT_MQ_HOST,
       rabbit_port=RABBIT_MQ_PORT,
       rabbit_login=RABBIT_MQ_LOGIN,
       rabbit_password=RABBIT_MQ_PASSWORD,
       redis_prefix=REDIS_PREFIX
   )
   ```
   - This connects the model to the task queue and result storage.
   - Ensure the environment variables match the corresponding API configuration.

3. **Starting the Connection**:
   ```python
   llm_wrap.start_connection()
   ```
   - Begins consuming tasks from RabbitMQ and processes them using the selected model.
   - Results are saved to Redis.

---

## Environment Variable Configuration

Environment variables are defined in the `.env` file and passed to Docker Compose. Below are the required variables:

```plaintext
TOKENS_LEN=16384
GPU_MEMORY_UTILISATION=0.9
TENSOR_PARALLEL_SIZE=2
MODEL_PATH=/data/<your_model_path>
NVIDIA_VISIBLE_DEVICES=<your_GPUs>
REDIS_HOST=localhost
REDIS_PORT=6379
QUEUE_NAME=<your_queue_name>
RABBIT_MQ_HOST=<rabbitmq_host>
RABBIT_MQ_PORT=<rabbitmq_port>
RABBIT_MQ_LOGIN=<rabbitmq_login>
RABBIT_MQ_PASSWORD=<rabbitmq_password>
REDIS_PREFIX=<redis_key_prefix>
```

### Synchronization with API

If you are deploying an API in another container, ensure the following:
1. **Environment Variables**:
   - Match the Redis and RabbitMQ configuration between the API and the LLM containers (e.g., `REDIS_HOST`, `RABBIT_MQ_HOST`).

2. **Network**:
   - Both containers must be on the same Docker network (`llm_wrap_network` in this example).

3. **Shared Queues**:
   - The `QUEUE_NAME` variable should be consistent across containers to ensure tasks are properly routed.

---

## Running the System

1. **Setup Docker Compose**:
   - Adjust `docker-compose.yml` and `.env` with your specific configuration.
   - Start the system:
     ```bash
     docker-compose up -d
     ```

2. **Verify Running Containers**:
   - Check active containers:
     ```bash
     docker ps
     ```

3. **Monitor Logs**:
   - To view logs for a specific container:
     ```bash
     docker logs -f <container_name>
     ```

4. **Submit Tasks**:
   - Tasks can be submitted to the RabbitMQ queue, and results will be saved in Redis.

---

For more details, refer to the comments in `docker-compose.yml` and `main.py`. If you encounter any issues, feel free to open an issue in the repository!

