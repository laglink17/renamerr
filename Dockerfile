FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements and app files
COPY requirements.txt ./
COPY app.py ./
# Copy templates directory
COPY templates ./templates

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Add default values for UID and GID
ENV PUID=1000
ENV PGID=100

# Expose port for Flask
EXPOSE 5000

# Command to run the app
CMD ["python", "app.py"]
