FROM arm64v8/gcc

RUN apt update && apt install -y device-tree-compiler cpio imagemagick p7zip-full python3-pip

RUN mkdir /asahi
WORKDIR /asahi

CMD ["./build.sh"]