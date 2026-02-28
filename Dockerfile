FROM python:3.14-bookworm

# Update OS packages
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y build-essential libffi-dev libssl-dev python3-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Virtual environment
ENV VENV_PATH=/app/venv
ENV PATH="$VENV_PATH/bin:$PATH"

RUN python -m venv $VENV_PATH \
    && $VENV_PATH/bin/pip install --upgrade pip

# Copy dependencies
COPY requirements.txt /tmp/requirements.txt
RUN $VENV_PATH/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# Copy server + config into image
COPY server.py config.py ./

EXPOSE 8567

CMD ["python", "server.py"]