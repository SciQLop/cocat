#!/usr/bin/env bash
set -e
BASEDIR=$(dirname "$0")

BUILD_TYPE=${1:-"testing"}
if [ "$BUILD_TYPE" = "release" ]; then
    BUILD_ARG_FILE="release.conf"
    TAG=stable
else
    BUILD_ARG_FILE="testing.conf"
    TAG=devel
fi

if [ -z "${container}" ]; then
    REMOTE=""
else
    REMOTE="--remote"
fi

docker $REMOTE build --build-arg-file=$BUILD_ARG_FILE  -t 129.104.6.172:32219/sciqlop/cocat-server:$TAG -f docker/Dockerfile $BASEDIR/..
docker $REMOTE push 129.104.6.172:32219/sciqlop/cocat-server:$TAG

