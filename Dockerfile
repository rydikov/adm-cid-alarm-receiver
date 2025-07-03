FROM python:3.13.3-slim

ENV TZ Europe/Moscow
ENV PYTHONDONTWRITEBYTECODE yes

WORKDIR /app

COPY requires.txt requires.txt
RUN python3 -m pip install --upgrade pip
RUN pip install -r requires.txt

COPY event_codes.json event_codes.json
COPY server.py server.py

