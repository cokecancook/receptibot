# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY ./src/agents/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
# We need to copy the entire src directory to have access to the agent code
COPY ./src /app/src

# Expose the port the app runs on
EXPOSE 8000

# Define the command to run the application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "src.agents.api.main:app"]