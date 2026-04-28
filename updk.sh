#!/bin/bash

set -e

PROJECT_DIR="/Users/zyy/Documents/fodhelper"
IMAGE_NAME="fodhelper:latest"
TAR_NAME="fodhelper.tar"
REMOTE_USER="root"
REMOTE_HOST="192.168.200.203"
REMOTE_DIR="/www/server/docker_project"

export https_proxy=http://127.0.0.1:64630 http_proxy=http://127.0.0.1:64630 all_proxy=socks5://127.0.0.1:64630

echo "进入项目目录..."
cd ${PROJECT_DIR}

echo "开始构建Docker镜像..."
docker build --platform=linux/amd64 -t ${IMAGE_NAME} . --no-cache

echo "导出Docker镜像为tar包..."
docker save ${IMAGE_NAME} -o ${TAR_NAME}

echo "开始传输到远程服务器..."
scp ${PROJECT_DIR}/${TAR_NAME} ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}

echo "✅ 操作完成：镜像已构建、导出并上传成功"
