FROM python:3.12-slim

WORKDIR /app
COPY rsvp.py .

ENV TERM=xterm-256color
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "rsvp.py"]
