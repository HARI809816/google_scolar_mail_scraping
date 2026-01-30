FROM python:3.10-slim

# Install Chromium + Driver
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libxkbcommon0 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    libxshmfence1 \
    libu2f-udev \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Set Chromium paths
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_BIN=/usr/bin/chromedriver

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt


COPY . .

EXPOSE 6000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "6000"]
    