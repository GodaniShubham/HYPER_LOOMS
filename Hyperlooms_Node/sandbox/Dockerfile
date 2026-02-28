FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /sandbox

RUN pip install --no-cache-dir httpx==0.27.2

COPY runner.py /sandbox/runner.py

ENTRYPOINT ["python", "/sandbox/runner.py"]
