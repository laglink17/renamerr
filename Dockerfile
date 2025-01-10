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

# Expose port for Flask
EXPOSE 5000

# Command to run the app
CMD ["python", "app.py"]
