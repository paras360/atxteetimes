# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file first, for better caching
COPY requirements.txt .

# Install the dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# Install Playwright and its dependencies
RUN apt-get update && apt-get install -y \
  libnss3 \
  libatk-bridge2.0-0 \
  libxcomposite1 \
  libxrandr2 \
  libxdamage1 \
  libxkbcommon0 \
  libgbm1 \
  libgtk-3-0 \
  libasound2 \
  && rm -rf /var/lib/apt/lists/*

# Install Playwright browsers
RUN pip install playwright
RUN playwright install --with-deps

# Expose the port on which Streamlit will run
EXPOSE 8501

# Run the Streamlit app when the container launches
CMD ["streamlit", "run", "streamlit_app.py"]