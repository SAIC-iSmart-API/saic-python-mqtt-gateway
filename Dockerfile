FROM python:3.12-slim

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc python3-dev \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc python3-dev
# the --no-install-recommends helps limit some of the install so that you can be more explicit about what gets installed

COPY . .

CMD [ "python", "./mqtt_gateway.py"]
