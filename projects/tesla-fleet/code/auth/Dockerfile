FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY app.py /app/app.py
EXPOSE 8000
CMD ["python", "/app/app.py", "serve"]
