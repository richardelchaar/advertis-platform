# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables to prevent Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /code

# Copy the requirements file into the container at the root of the WORKDIR
COPY ./requirements.txt /code/requirements.txt

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy the application code into the container
COPY ./app /code/app
COPY ./scripts /code/scripts

# Copy and prepare the entrypoint script
COPY ./entrypoint.sh /code/entrypoint.sh
RUN chmod +x /code/entrypoint.sh
ENTRYPOINT ["/code/entrypoint.sh"]

# This CMD now becomes the default command that gets passed TO the entrypoint script
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]