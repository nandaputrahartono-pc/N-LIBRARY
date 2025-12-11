#!/bin/bash
curl -L -o ffmpeg.tar.xz https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar -xf ffmpeg.tar.xz
mv ffmpeg-*-static/ffmpeg ./ffmpeg
chmod +x ./ffmpeg
