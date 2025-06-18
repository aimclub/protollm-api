FROM nginx/unit:1.28.0-python3.10

# Установка зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends git

# Рабочая директория
WORKDIR /app

# Копируем зависимости и устанавливаем
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копируем код (измените пути на корректные)
COPY ./protollm_api ./protollm_api
COPY ./unit_config.json /docker-entrypoint.d/config.json

# Unit будет автоматически запускать API по конфигу
# Для воркера используем отдельный entrypoint