FROM python:3.13-alpine3.22

ARG S6_OVERLAY_VERSION=3.2.3.2
ARG TARGETARCH
ARG ALPINE_MIRROR=https://dl-cdn.alpinelinux.org/alpine

RUN sed -i "s#https://dl-cdn.alpinelinux.org/alpine#${ALPINE_MIRROR}#g" /etc/apk/repositories \
    && apk add --no-cache mosquitto mosquitto-clients curl tzdata xz \
    && addgroup -g 1000 homemind \
    && adduser -D -H -u 1000 -G homemind homemind

COPY vendor/s6-overlay-noarch.tar.xz /tmp/s6-overlay-noarch.tar.xz
COPY vendor/s6-overlay-x86_64.tar.xz /tmp/s6-overlay-x86_64.tar.xz
COPY vendor/s6-overlay-aarch64.tar.xz /tmp/s6-overlay-aarch64.tar.xz
RUN tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz \
    && case "${TARGETARCH:-arm64}" in \
         amd64) tar -C / -Jxpf /tmp/s6-overlay-x86_64.tar.xz ;; \
         arm64) tar -C / -Jxpf /tmp/s6-overlay-aarch64.tar.xz ;; \
         *) echo "Unsupported TARGETARCH: ${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && rm /tmp/s6-overlay-*.tar.xz

WORKDIR /opt/homemind-air
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
COPY rootfs /
COPY scripts/healthcheck.sh /usr/local/bin/homemind-healthcheck

ENV TZ=Asia/Shanghai \
    S6_READ_ONLY_ROOT=1 \
    S6_BEHAVIOUR_IF_STAGE2_FAILS=2 \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=60000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["/usr/local/bin/homemind-healthcheck"]

ENTRYPOINT ["/init"]
