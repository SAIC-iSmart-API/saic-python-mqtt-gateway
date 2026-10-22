ARG POETRY_VERSION=2.5.1
ARG PYTHON_VERSION=3.14

FROM nanomad/poetry:${POETRY_VERSION}-python-${PYTHON_VERSION} AS builder

WORKDIR /usr/src/app

# --- Reproduce the environment ---
# You can comment the following two lines if you prefer to manually install
#   the dependencies from inside the container.
COPY pyproject.toml poetry.lock /usr/src/app/

# Install the dependencies and clear the cache afterwards.
#   This may save some MBs.
RUN poetry install --no-root --only main && rm -rf $POETRY_CACHE_DIR

# Now let's build the runtime image from the builder.
#   We'll just copy the env and the PATH reference.
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG RELEASE_VERSION=latest

LABEL saic.mqtt.gateway.version="${RELEASE_VERSION}"
LABEL saic.mqtt.gateway.description="SAIC MQTT Gateway: A Python-based service that queries the SAIC API, processes the data, and publishes it to an MQTT broker."

WORKDIR /usr/src/app

ENV RELEASE_VERSION=${RELEASE_VERSION}
ENV VIRTUAL_ENV=/usr/src/app/.venv
ENV PATH="/usr/src/app/.venv/bin:$PATH"

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY src/ .
COPY examples/ .

USER 185:185

CMD [ "python", "./main.py"]