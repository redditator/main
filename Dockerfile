FROM python:3.10-slim

WORKDIR /app
LABEL owner=redditator

# install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    espeak-ng \
    curl \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# install ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# create python virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# install python dependencies
COPY requirements .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements

# copy application code
COPY . .

# copy and setup entrypoint script
COPY redditator.sh /redditator.sh
RUN chmod +x /redditator.sh

ENTRYPOINT ["/redditator.sh"]