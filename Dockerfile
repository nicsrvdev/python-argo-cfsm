# syntax=docker/dockerfile:1
# ============================================================
# Python-Argo-Cfsm
#   - app.py 运行入口；app-src.py 可读源码
#   - 构建时固化 web / bot / cfprobe 到 /opt/bin
#   - 运行时优先复制内置为随机名；缺失才下载
# ============================================================
# 注意：上游 cfsm-agent 的 go.mod 自 2026-10-21（cbd0836）起要求 go >= 1.27.3，
# 1.26 构建会以 "go.mod requires go >= 1.27.3 (running go 1.26.10; GOTOOLCHAIN=local)"
# 失败（2026-11-08 构建 42461022902 就是这么挂的）。上游再升 Go 版本时这里要跟着升。
FROM golang:1.27.3-alpine AS binbuilder
ARG TARGETPLATFORM
ARG CFSM_AGENT_REPO=https://github.com/huilang-me/cfsm-agent.git
# 可选：构建时校验下载的二进制（docker build --build-arg XRAY_SHA256=...）
ARG XRAY_SHA256=""
ARG CLOUDFLARED_SHA256=""
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
    if [ -n "$XRAY_SHA256" ]; then echo "$XRAY_SHA256  /opt/bin/web" | sha256sum -c -; fi; \
    if [ -n "$CLOUDFLARED_SHA256" ]; then echo "$CLOUDFLARED_SHA256  /opt/bin/bot" | sha256sum -c -; fi; \
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
# 只留真正用到的包：openssl（证书指纹）+ curl（取公网 IP 的兜底）+ ca-certificates；
# bash / iproute2 / coreutils / gcompat 在 app.py 里没有任何调用，已砍掉。
RUN apk add --no-cache openssl curl ca-certificates

COPY --from=binbuilder /opt/bin/web /opt/bin/web
COPY --from=binbuilder /opt/bin/bot /opt/bin/bot
COPY --from=binbuilder /opt/bin/cfprobe /opt/bin/cfprobe

# app-src.py 是仓库里的干净源码，不进镜像（与 app.py 完全重复，省一份拷贝）
COPY app.py requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt && chmod +x /app/app.py

# 压 Go 二进制（cloudflared / cf-probe）的堆增长，省内存；GOGC 越小回收越勤
ENV GOGC=20 GOMEMLIMIT=64MiB

EXPOSE 3000/tcp
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:${PORT:-3000}/ || exit 1
# 注意：容器重启策略不在镜像里，见 docker-compose.yml 的 restart: unless-stopped
# （主进程被杀 / 宿主机重启后由 Docker 拉起整个容器；容器内的子进程由 app.py 看门狗管）
CMD ["python3", "/app/app.py"]
