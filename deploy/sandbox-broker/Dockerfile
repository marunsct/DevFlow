# The sandbox broker (deep review 2026-11-18, item E1b): in place of `docker-proxy`, a Docker API endpoint that passes
# on only the calls the sandbox makes and only a container create shaped like the sandbox's (see validator.py).
# Standard library only. It talks to the Docker socket, so it runs as root inside its container: give it a read-only
# root, no capabilities and a network only the worker joins (see the commented block in docker-compose.sandbox.yml).
FROM python:3.12-slim

WORKDIR /broker
COPY validator.py broker.py ./

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 2375
CMD ["python", "-I", "/broker/broker.py"]
