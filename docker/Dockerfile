FROM fedora:43
LABEL authors="jeandet"

ARG PORT=6570

ENV STORAGE_PATH=/storage \
    DB_PATH=/db \
    LOG_PATH=/log \
    PORT=$PORT

RUN useradd cocat && mkdir -p $STORAGE_PATH $DB_PATH  $LOG_PATH/cocat \
    && chown -R cocat $STORAGE_PATH $DB_PATH  $LOG_PATH \
    && dnf install -y git python3 \
    && dnf clean all

USER cocat
WORKDIR /home/cocat



RUN python3 -m ensurepip \
    && python3 -mpip install -U pip \
    && python3 -mpip install -U cocat["server"]

ADD entry_point.sh /home/cocat/entry_point.sh
ADD create-user.sh /usr/local/bin/create-user

VOLUME $STORAGE_PATH
VOLUME $LOG_PATH
VOLUME $DB_PATH
EXPOSE $PORT/tcp

ENTRYPOINT ["/home/cocat/entry_point.sh"]