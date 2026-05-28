FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY generation/ ./generation/
COPY backend/   ./backend/
COPY templates/ ./templates/
COPY knowledge_base/ ./knowledge_base/
COPY app.py .

# Pre-generate data at build time so there is no cold-start penalty on Cloud Run
RUN python generation/generate.py \
 && python backend/pipeline/01_clean.py \
 && python backend/pipeline/02_features.py \
 && python backend/pipeline/03_score.py \
 && python backend/pipeline/04_rank.py

ENV PORT=8080
EXPOSE 8080

CMD gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --timeout 120 app:app
