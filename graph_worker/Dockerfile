FROM python:3.11-slim

WORKDIR /app

COPY graph_worker/pyproject.toml /app/pyproject.toml

RUN pip install --no-cache-dir uv && uv pip install --system \
    fastapi \
    "uvicorn[standard]" \
    pydantic \
    leidenalg \
    igraph

COPY graph_worker/main.py /app/main.py

EXPOSE 8090

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8090"]
