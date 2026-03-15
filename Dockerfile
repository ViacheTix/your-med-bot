# Telegram-бот записи на приём (АСМС)
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONPATH=/app
# Часовой пояс Москва
ENV TZ=Europe/Moscow
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py entrypoint.py ingest.py ./
COPY db ./db
COPY bot ./bot
COPY llm ./llm
COPY scripts ./scripts
COPY doctor ./doctor
COPY data ./data
COPY disease_anamnesis_database_cleaned.json ./
COPY main.py ./

# БД по умолчанию в /data для монтирования тома
ENV DB_PATH=/data/bot.db

ENTRYPOINT ["python", "entrypoint.py"]
