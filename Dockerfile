FROM python:3.12-slim

RUN pip install --no-cache-dir pymupdf==1.25.5

WORKDIR /app
COPY rsvp.py pre_read.py ./

ENV TERM=xterm-256color
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "rsvp.py"]
