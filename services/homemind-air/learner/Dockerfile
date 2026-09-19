FROM python:3.13-slim

WORKDIR /opt/homemind-air-learner
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY learner.py ./

RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin homemind
USER homemind

ENV HOMEMIND_DB=/data/homemind-air.sqlite3 \
    MODEL_PATH=/data/adaptive_model.json \
    LOOKBACK_DAYS=30 \
    LEARN_INTERVAL_SECONDS=900 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

CMD ["python", "/opt/homemind-air-learner/learner.py"]
