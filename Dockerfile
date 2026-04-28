FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=7860

# Install system dependencies
USER root
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-noto-core \
    fonts-noto-ui-core \
    fonts-noto-extra \
    imagemagick \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Fix ImageMagick policy (Updated to work for any ImageMagick version)
RUN find /etc/ImageMagick-* -name "policy.xml" -exec sed -i 's/domain="path" rights="none" pattern="@\*"/domain="path" rights="read|write" pattern="@\*"/g' {} +

# Set up a non-root user (Required by Hugging Face)
RUN useradd -m -u 1000 user
WORKDIR /app

# Ensure Tamil font is in the expected location
RUN mkdir -p /usr/share/fonts/truetype/noto/
RUN ln -s /usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf /usr/share/fonts/truetype/noto/NotoSansTamil-Bold.ttf || true

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application and set ownership
COPY --chown=user:user . .

# Create necessary directories and set permissions
RUN mkdir -p output data logs credentials assets/fonts assets/music assets/watermark \
    && chown -R user:user /app

# Switch to non-root user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

# Expose the port
EXPOSE 7860

# Run the server
CMD ["python", "server.py"]
