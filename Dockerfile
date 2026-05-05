FROM python:3.12-slim

RUN pip install --no-cache-dir pymupdf==1.25.5 anthropic

WORKDIR /app
COPY rsvp.py pre_read.py detect_equations.py ./

ENV TERM=xterm-256color
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "rsvp.py"]
