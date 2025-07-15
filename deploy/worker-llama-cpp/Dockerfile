FROM ubuntu:22.04

RUN apt update && apt upgrade -y
RUN apt install pip -y
RUN apt install python3 -y
RUN apt install git -y

RUN apt install build-essential -y
RUN apt install gcc-11 g++-11 -y

COPY ../../temp/llm-worker/requirements.txt ./requirements.txt

RUN pip install -r requirements.txt

COPY ../../temp/llm-worker .

CMD python3 main.py
