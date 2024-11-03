FROM python:3.10

# Set pip to have cleaner logs and no saved cache
ENV PIP_NO_CACHE_DIR=false

RUN mkdir -p /bot
WORKDIR bot

RUN pip install poetry

COPY ./pyproject.toml /code/pyproject.toml
COPY ./poetry.lock /code/poetry.lock

RUN poetry install

COPY . /bot

CMD python3 main.py