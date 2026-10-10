# Build stage / Runtime
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime dependencies and security updates
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 10001 bnb && \
    useradd -u 10001 -g bnb -s /bin/bash -m bnb

WORKDIR /app

# Copy dependency definition and install
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application source code and card assets
COPY bnb/ ./bnb/
COPY decks/ ./decks/
COPY main.py .

# Set ownership to unprivileged user
RUN chown -R bnb:bnb /app

USER bnb

# Healthcheck to verify Python process integrity
HEALTHCHECK --interval=60s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import bnb; from bnb.deck_loader import DeckLoader; dl = DeckLoader('decks'); dl.load_all_decks(); assert len(dl.list_decks()) == 10" || exit 1

# Start the bot
CMD ["python", "main.py"]
