# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables to prevent Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /code

# Copy the requirements file into the container
COPY ./requirements.txt /code/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy the application code into the container
COPY ./app /code/app

# Command to run the Streamlit application
# --server.port 8000 makes it run on the port we defined in docker-compose
# --server.address 0.0.0.0 makes it accessible from outside the container
CMD ["streamlit", "run", "app/app.py", "--server.port=8000", "--server.address=0.0.0.0"]