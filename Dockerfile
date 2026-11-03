FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[dev]'
COPY config ./config
COPY examples ./examples
COPY tests ./tests
CMD ["tokenops-demo", "--scenario", "all"]
