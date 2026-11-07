FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home cqa && mkdir /data && chown cqa /data
ENV DATABASE_URL=sqlite:////data/cqa-foundation.db LLM_PROVIDER=mock
USER cqa
EXPOSE 8000
CMD ["python", "-m", "cqa.backend", "serve", "--host", "0.0.0.0"]
