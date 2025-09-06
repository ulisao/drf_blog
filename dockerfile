FROM python:3.9

# install ssh client
RUN apt-get update && apt-get install -y openssh-client

# set environment variables
ENV PYTHONUNBUFFERED 1

# set work directory
WORKDIR /app

# copy requirements.txt
COPY requirements.txt /app/

# install dependencies
RUN pip install -r requirements.txt

# copy project
COPY . /app/

# start ssh tunnel
CMD python manage.py runserver 0.0.0.0:8000