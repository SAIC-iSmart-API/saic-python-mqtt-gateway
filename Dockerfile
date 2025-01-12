ARG POETRY_VERSION=1.8.3
ARG PYTHON_VERSION=3.12

FROM weastur/poetry:${POETRY_VERSION}-python-${PYTHON_VERSION} AS builder

ENV POETRY_HOME=/opt/poetry
ENV POETRY_NO_INTERACTION=1
ENV POETRY_VIRTUALENVS_IN_PROJECT=1
ENV POETRY_VIRTUALENVS_CREATE=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Tell Poetry where to place its cache and virtual environment
ENV POETRY_CACHE_DIR=/opt/.cache

# Install build-time deps for poetry and FFI
RUN apt-get update  \
    && apt-get install -y --no-install-recommends \
            build-essential \
            g++ \
            gcc \
            libffi-dev \
            libssl-dev \
            pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

# --- Reproduce the environment ---
# You can comment the following two lines if you prefer to manually install
#   the dependencies from inside the container.
COPY pyproject.toml poetry.lock /usr/src/app/

# Install the dependencies and clear the cache afterwards.
#   This may save some MBs.
RUN --mount=type=tmpfs,target=/root/.cargo poetry install --no-root && rm -rf $POETRY_CACHE_DIR

# Now let's build the runtime image from the builder.
#   We'll just copy the env and the PATH reference.
FROM python:${PYTHON_VERSION}-slim AS runtime

WORKDIR /usr/src/app

ENV VIRTUAL_ENV=/usr/src/app/.venv
ENV PATH="/usr/src/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY src/ .
COPY examples/ .

CMD [ "python", "./mqtt_gateway.py"]