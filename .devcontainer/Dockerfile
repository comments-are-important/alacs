FROM mcr.microsoft.com/devcontainers/python:3 AS code
CMD [ "/usr/bin/sleep", "inf" ]
WORKDIR /opt/workdir
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
  pip3 --disable-pip-version-check install -r requirements.txt
