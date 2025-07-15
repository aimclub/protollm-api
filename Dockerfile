FROM nginx/unit:1.28.0-python3.10

RUN apt-get update && apt-get install -y --no-install-recommends git

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY protollm_api ./protollm_api
COPY deploy/api/unit_config.json /docker-entrypoint.d/config.json

