FROM node:18
WORKDIR /app
COPY ["package.json", "./"]
RUN apt update
RUN apt install python -y
# RUN npm install -g node-pre-gyp
# RUN npm install -g npm@8.9.0
RUN npm install
