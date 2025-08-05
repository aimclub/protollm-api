FROM nginx/unit:1.28.0-python3.10

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends git

# Working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the code (adjust paths if needed)
COPY ./protollm_api ./protollm_api
COPY ./unit_config.json /docker-entrypoint.d/config.json

# Unit will automatically start the API using the config
# For the worker, use a separate entrypoint