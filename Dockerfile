FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file first for better caching
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Ensure apt is updated and install wget and gpg for key management
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https \
    ca-certificates \
    gnupg \
    wget

# Add the Docker public key and ensure the system is updated securely
RUN wget -q -O - https://deb.debian.org/debian-archive/debian-archive-keyring.gpg | apt-key add -

# Install Playwright and its dependencies
RUN pip install playwright
RUN playwright install-deps
RUN playwright install --with-deps

# Copy the rest of the application code
COPY . .

# Expose the port on which Streamlit will run
EXPOSE 8501

# Run the Streamlit app when the container launches
CMD ["streamlit", "run", "streamlit_app.py"]