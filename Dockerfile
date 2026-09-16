# syntax=docker/dockerfile:1
# ============================================================
# Python-Argo-Cfsm
#   - app.py 运行入口；app-src.py 可读源码
#   - 构建时固化 web / bot / cfprobe 到 /opt/bin
#   - 运行时优先复制内置为随机名；缺失才下载
# ============================================================
FROM golang:1.26-alpine AS binbuilder
ARG TARGETPLATFORM
ARG CFSM_AGENT_REPO=https://github.com/huilang-me/cfsm-agent.git
RUN apk add --no-cache curl ca-certificates git >/dev/null && mkdir -p /opt/bin

RUN case "$TARGETPLATFORM" in \
      "linux/amd64") echo "amd" > /arch ;; \
      "linux/arm64") echo "arm" > /arch ;; \
      *) echo "amd" > /arch ;; \
    esac

RUN ARCH=$(cat /arch); \
    for BIN in web bot; do \
      for URL in "https://${ARCH}64.oooen.com/${BIN}" "https://${ARCH}64.ssss.nyc.mn/${BIN}"; do \
        echo ">>> downloading ${BIN} from ${URL}"; \
        if curl -fsSL --connect-timeout 15 -o "/opt/bin/${BIN}" "${URL}"; then break; fi; \
      done; \
    done; \
    chmod +x /opt/bin/web /opt/bin/bot && \
    ls -la /opt/bin

RUN git clone --depth 1 "$CFSM_AGENT_REPO" /src/cfsm-agent && \
    cd /src/cfsm-agent && \
    case "$TARGETPLATFORM" in \
      "linux/amd64") GOARCH=amd64 ;; \
      "linux/arm64") GOARCH=arm64 ;; \
      *) GOARCH=amd64 ;; \
    esac && \
    CGO_ENABLED=0 GOOS=linux GOARCH=$GOARCH \
      go build -trimpath -ldflags "-s -w -X main.version=9.9.9" -o /opt/bin/cfprobe ./cmd/cf-probe && \
    chmod +x /opt/bin/cfprobe && \
    rm -rf /src

FROM python:3.10-alpine
WORKDIR /app
RUN apk update && apk upgrade && \
    apk add --no-cache openssl curl bash gcompat iproute2 coreutils ca-certificates && \
    chmod +x /tmp || true

COPY --from=binbuilder /opt/bin/web /opt/bin/web
COPY --from=binbuilder /opt/bin/bot /opt/bin/bot
COPY --from=binbuilder /opt/bin/cfprobe /opt/bin/cfprobe

COPY app.py requirements.txt /app/
COPY app-src.py /app/app-src.py
RUN pip install --no-cache-dir -r requirements.txt && chmod +x /app/app.py

EXPOSE 3000/tcp
CMD ["python3", "/app/app.py"]
