FROM python:3.10-slim

# Set pip to have cleaner logs and no saved cache
ENV PIP_NO_CACHE_DIR=false

RUN mkdir -p /bot
WORKDIR bot

COPY ./requirements.txt /bot/requirements.txt
RUN pip3 install -r requirements.txt

COPY . /bot

CMD python3 main.py