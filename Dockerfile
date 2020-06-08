FROM python:3.8-slim

EXPOSE 5000

# This prevents Python from writing out pyc files
ENV PYTHONDONTWRITEBYTECODE 1
# This keeps Python from buffering stdin/stdout
ENV PYTHONUNBUFFERED 1

ARG APT_FLAGS_COMMON="-y"
ARG APT_FLAGS_PERSISTENT="${APT_FLAGS_COMMON} --no-install-recommends"
ARG APT_FLAGS_DEV="${APT_FLAGS_COMMON} --no-install-recommends"
RUN set -eux && \
    apt-get ${APT_FLAGS_COMMON} update && \
    DEBIAN_FRONTEND=noninteractive apt-get ${APT_FLAGS_DEV} install \
    curl && \
    apt-get ${APT_FLAGS_COMMON} autoremove && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --create-home app
# RUN addgroup -S app && adduser -S app -G app
USER app
ENV APP_HOME=/home/app
WORKDIR $APP_HOME

# setup environment
RUN curl -ksSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python
# RUN wget -O - https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python
COPY --chown=app:app poetry.lock pyproject.toml ./
RUN $APP_HOME/.poetry/bin/poetry install --no-dev --no-root

# RUN --mount=type=cache,target=/home/app/.cache/pip python3 -m pip install .

# copy app
COPY --chown=app:app debugtoolkit/*.py debugtoolkit/
COPY --chown=app:app vfzsync/__*.py vfzsync/vfz_*.py vfzsync/
COPY --chown=app:app vfzsync/lib/*.py vfzsync/lib/
COPY --chown=app:app vfzsync/static vfzsync/static
COPY --chown=app:app vfzsync/templates vfzsync/templates

COPY --chown=app:app entrypoint.sh ./
RUN chmod +rx $APP_HOME/entrypoint.sh

ENTRYPOINT [ "/home/app/entrypoint.sh", "web", "prod" ]
# ENTRYPOINT [ "/home/app/entrypoint.sh", "web", "dev" ]
# ENTRYPOINT [ "/home/app/entrypoint.sh", "script", "dev" ]
# ENTRYPOINT [ "/home/app/entrypoint.sh", "debug", "dev" ]
