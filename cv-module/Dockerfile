# cv-module/Dockerfile
#
# python:3.11-slim is used instead of 3.12 because MediaPipe 0.10.x
# wheels for Linux ARM are only reliably available for 3.11.
FROM python:3.11-slim

# System libs required by OpenCV and MediaPipe native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first — separate layer improves rebuild cache hits
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY modules/ ./modules/

# Run as non-root for security
RUN useradd -m cvuser && chown -R cvuser /app
USER cvuser

CMD ["python", "main.py"]
