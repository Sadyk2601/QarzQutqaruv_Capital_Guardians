FROM python:3.12-slim
# LightGBM needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=user app ./app
COPY --chown=user model/__init__.py model/features.py ./model/
COPY --chown=user model/artifacts ./model/artifacts
COPY --chown=user data/demo_portfolio.json ./data/demo_portfolio.json
USER user
ENV AUDIT_DB_PATH=/tmp/audit.db PYTHONUNBUFFERED=1 PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
