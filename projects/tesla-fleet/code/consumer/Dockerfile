FROM python:3.12-slim
RUN pip install --no-cache-dir "confluent-kafka==2.*" "psycopg[binary]==3.*"
COPY consumer.py /app/consumer.py
USER nobody
CMD ["python", "-u", "/app/consumer.py"]
