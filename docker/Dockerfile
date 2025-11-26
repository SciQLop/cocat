FROM fedora:43
LABEL authors="jeandet"

ARG PORT=6570
ARG COCAT=.

ENV STORAGE_PATH=/storage \
    DB_PATH=/db \
    LOG_PATH=/log \
    PORT=$PORT \
    COCAT_PROXY_PREFIX=""

RUN useradd cocat && mkdir -p $STORAGE_PATH $DB_PATH  $LOG_PATH/cocat \
    && chown -R cocat $STORAGE_PATH $DB_PATH  $LOG_PATH \
    && dnf install -y git python3 \
    && dnf clean all


COPY *.cfg *.yaml *.toml *.txt *.md LICENSE /home/cocat/cocat/
COPY src /home/cocat/cocat/src
RUN chown -R cocat /home/cocat/cocat


USER cocat
WORKDIR /home/cocat



RUN python3 -m ensurepip \
    && python3 -mpip install -U pip \
    && cd cocat \
    && python3 -mpip install -U .["server"] \
    && cd - \
    && rm -rf /home/cocat/cocat

ADD docker/entry_point.sh /home/cocat/entry_point.sh
ADD docker/create-user.sh /usr/local/bin/create-user
ADD docker/add-user-to-room.sh /usr/local/bin/add-user-to-room
ADD docker/remove-user-from-room.sh /usr/local/bin/remove-user-from-room

VOLUME $STORAGE_PATH
VOLUME $LOG_PATH
VOLUME $DB_PATH
EXPOSE $PORT/tcp

ENTRYPOINT ["/home/cocat/entry_point.sh"]