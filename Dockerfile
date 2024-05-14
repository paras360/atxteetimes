FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file first, for better caching
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Ensure apt is updated and necessary packages are installed
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    gnupg \
    wget

# Fix missing GPG keys and install essential system libraries needed by Playwright
RUN wget -q -O - https://deb.debian.org/debian-archive/debian-archive-keyring.gpg | apt-key add - && \
    apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxkbcommon0 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright and its browsers
RUN pip install playwright
RUN playwright install --with-deps

# Copy the rest of the application code
COPY . .

# Expose the port on which Streamlit will run
EXPOSE 8501
