FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FASTEMBED_CACHE_PATH=/model_cache

WORKDIR /srv

RUN useradd --create-home --uid 10001 vouch

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The reranker is ~90MB and downloads on first use. Fetching it here
# means a fresh container answers its first question at full speed.
RUN python -c "from fastembed.rerank.cross_encoder import TextCrossEncoder; \
TextCrossEncoder(model_name='Xenova/ms-marco-MiniLM-L-6-v2')" \
    && chown -R vouch:vouch /model_cache

# schema.sql sits in app/db/, so copying app/ brings it along. No
# frontend/ — that is deployed separately, on its own host.
COPY --chown=vouch:vouch app/ ./app/

# The API writes uploads here and the worker reads them, so compose
# mounts one volume across both.
RUN mkdir -p temp_uploads && chown vouch:vouch temp_uploads

USER vouch
EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
