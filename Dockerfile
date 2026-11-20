FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Chromium lets kaleido render chart PNGs (used by the Streamlit export button).
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium \
    && rm -rf /var/lib/apt/lists/*
COPY src/ src/
COPY dashboard/ dashboard/
COPY app.py .
ENV PYTHONPATH=/app/src
ENTRYPOINT ["python", "-m", "agent.main"]
