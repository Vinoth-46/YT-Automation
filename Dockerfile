# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Install system dependencies (FFmpeg is crucial for video automation)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create necessary directories
RUN mkdir -p assets outputs temp credentials

# Expose the port for Render's health check
EXPOSE 8000

# Command to run the bot
CMD ["python", "bot/main.py"]

