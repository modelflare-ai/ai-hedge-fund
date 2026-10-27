FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.5 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app
COPY pyproject.toml poetry.lock README.md ./
COPY hedge_fund ./hedge_fund

RUN poetry install --only main --no-ansi

VOLUME /root/.hedge-fund
EXPOSE 8000
CMD ["poetry", "run", "aihf-web"]
