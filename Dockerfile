ARG POETRY_VERSION=2.1.3
ARG PYTHON_VERSION=3.12

FROM nanomad/poetry:${POETRY_VERSION}-python-${PYTHON_VERSION} AS builder

WORKDIR /usr/src/app

# --- Reproduce the environment ---
# You can comment the following two lines if you prefer to manually install
#   the dependencies from inside the container.
COPY pyproject.toml poetry.lock /usr/src/app/

# Install the dependencies and clear the cache afterwards.
#   This may save some MBs.
RUN poetry install --no-root && rm -rf $POETRY_CACHE_DIR

# Now let's build the runtime image from the builder.
#   We'll just copy the env and the PATH reference.
FROM python:${PYTHON_VERSION}-slim AS runtime

WORKDIR /usr/src/app

ENV VIRTUAL_ENV=/usr/src/app/.venv
ENV PATH="/usr/src/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY src/ .
COPY examples/ .

CMD [ "python", "./main.py"]