FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV TRADER_STATE_DIR=/app/state PYTHONUNBUFFERED=1
CMD ["python", "scripts/run.py", "--mode", "paper", "--strategy", "p1", "--universe", "research22", "--run-id", "p1_paper"]
