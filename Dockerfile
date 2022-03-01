FROM debian
RUN apt-get update && apt-get install -y git build-essential cpio p7zip-full imagemagick python3-certifi wget device-tree-compiler bison flex libssl-dev bc

WORKDIR asahi-installer
COPY .git .git
RUN git reset --hard HEAD

RUN ./build.sh
