FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./frontend/
RUN npm --prefix frontend ci
COPY frontend ./frontend
COPY src/cqa/checklist.json ./src/cqa/checklist.json
RUN npm --prefix frontend run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY --from=frontend /build/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir . && useradd --create-home cqa && mkdir /data && chown cqa /data
ENV DATABASE_URL=sqlite:////data/cqa-foundation.db LLM_PROVIDER=mock CQA_FRONTEND_DIR=/app/frontend/dist
USER cqa
EXPOSE 8000
CMD ["python", "-m", "cqa.backend", "serve", "--host", "0.0.0.0"]
