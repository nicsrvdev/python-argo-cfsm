# Python-Argo-Cfsm

基于 [eooce/python-xray-argo](https://github.com/eooce/python-xray-argo) 改造的 **Argo 隧道 + 多协议代理 + 服务器监控探针** Python 版。

保留原项目全部功能：Vless-Ws-Tls / Vmess-Ws-Tls / Trojan-Ws-Tls 三协议节点、Cloudflare Argo 固定/临时隧道、订阅生成与上传、Telegram 推送、Reality / Hysteria2 / Socks5 入站；将探针从 Nezha（哪吒 v0/v1）替换为 [CF-Server-Monitor](https://github.com/huilang-me/CF-Server-Monitor) 的 Go Probe（`cf-probe`，镜像内构建版本号 `9.9.9`）。

---

## 镜像

```bash
docker pull ghcr.io/nicsrvdev/python-argo-cfsm:latest
```

## 与原项目的差异

| 项目 | 原项目 | 本项目 |
|------|--------|--------|
| 探针 | Nezha（哪吒 v0/v1 自由选择） | **cf-probe**（CF-Server-Monitor） |
| 探针变量 | `NEZHA_SERVER/PORT/KEY` | `CFP_ID / CFP_SECRET / CFP_URL` 等 |
| xray / cloudflared | 运行时从私有 CDN 下载 | Docker 构建时下载并固化进镜像，PaaS 仍运行时下载 |
| cf-probe | - | Docker 构建时源码编译（版本 `9.9.9`）；PaaS 运行时从官方 Release 下载 |
| 防检测 | 随机文件名 + 90s 清理运行副本 | 保留 |

---

## 快速使用

```bash
docker run -d --name python-argo-cfsm \
  -e UUID="你的UUID" \
  -e CFP_ID="CF面板服务器ID" \
  -e CFP_SECRET="CF面板密钥" \
  -e CFP_URL="https://你的worker域名/update" \
  -e ARGO_AUTH="固定隧道token(留空=临时隧道)" \
  -e ARGO_DOMAIN="固定隧道域名(留空=临时隧道)" \
  -p 3000:3000 \
  ghcr.io/nicsrvdev/python-argo-cfsm:latest
```

- 书签首页：`http://<主机>:3000/`
- 订阅地址：`http://<主机>:3000/sub`

非 Docker（PaaS / 游戏平台玩具）：上传 `app.py` + `requirements.txt`，`pip install -r requirements.txt` 后 `python3 app.py`，变量用环境变量注入（见下表）。

---

## 部署

本项目的部署方式有三种，**凭据处理方式不同**：

- **方式一：常规 Python 环境**（例如游戏平台玩具）
  - 只需上传 `app.py` 和 `requirements.txt` 两个文件，`app.py` 授权 `777`，变量通过环境变量注入
- **方式二：文件 + 命令结合**
  - 上传 `app.py` 和 `requirements.txt`，先运行 `chmod +x app.py`，再运行 `pip install -r requirements.txt`，然后运行 `screen python3 app.py` 即可。提示 screen not found 说明 screen 未安装，Debian/Ubuntu 安装命令：`apt install -y screen`，CentOS 安装命令：`yum install -y screen`
- **方式三：Docker 部署**
  - 构建本仓库 `Dockerfile`，镜像推送到 `ghcr.io/<你的用户名>/python-argo-cfsm:latest`。支持镜像部署的平台推荐优先使用镜像（构建时已固化 `web` / `bot` / `cfprobe` 三二进制，运行时零下载）

> 三种方式都走环境变量注入；如 fork 后硬编码变量再公开，请注意不要把探针密钥、隧道 token 留在公开仓库。
- cf-probe 在容器/平台内以 `run -config` 前台模式运行（无需 systemd），三进程各自随机文件名，90 秒后清理运行副本（进程不受影响）

---

## 环境变量

### 通用

| 变量 | 默认 | 说明 |
|------|------|------|
| `UUID` | `20e6e496-cf19-45c8-b883-14f5e11cd9f1` | 节点 UUID（三协议共用，不同平台建议修改） |
| `UPLOAD_URL` | 空 | 订阅上传地址，例如 `https://merge.serv00.net` |
| `PROJECT_URL` | 空 | 项目分配 URL |
| `AUTO_ACCESS` | `false` | 自动访问保活，`true` 开启，需同时填写 `PROJECT_URL` |
| `ARGO_AUTH` | 空 | 固定隧道 token/json，留空=临时隧道 |
| `ARGO_DOMAIN` | 空 | 固定隧道域名，留空=临时隧道 |
| `ARGO_PORT` | `8001` | 隧道回源端口，固定隧道 token 需和 Cloudflare 后台设置一致 |
| `CFIP` | `saas.sin.fan` | 节点优选域名/IP |
| `CFPORT` | `443` | 优选域名端口 |
| `NAME` | 空 | 节点名称前缀，例如 `Koyeb Fly` |
| `S5_PORT` / `HY2_PORT` / `REALITY_PORT` | 空 | 额外协议端口，填写即开启 |
| `PORT` | `3000` | http 服务监听端口，也是订阅端口 |
| `SUB_PATH` | `sub` | 订阅路径 |
| `FILE_PATH` | `.cache` | 运行目录，节点存放路径 |
| `CHAT_ID` / `BOT_TOKEN` | 空 | Telegram 节点推送（两变量同填生效） |
| `SHOW_LOG` | `true` | 是否显示日志，默认显示，`false` / `disable` / `no` 屏蔽 |

### 探针（CF-Server-Monitor）

`CFP_ID + CFP_SECRET + CFP_URL` 三者同时填写才启动探针。

| 变量 | 默认 | 说明 |
|------|------|------|
| `CFP_ID` | 空 | 服务器 ID，CF 面板添加服务器后获取 |
| `CFP_SECRET` | 空 | 服务器密钥 |
| `CFP_URL` | 空 | Worker 上报地址，如 `https://example.com/update` |
| `CFP_INTERVAL` | `60` | 上报间隔（秒） |
| `CFP_COLLECT` | `0` | 采样间隔（秒），`0`=WSS 自动采样 |
| `CFP_CT` / `CFP_CU` / `CFP_CM` / `CFP_BD` | 空 | 电信/联通/移动/BGP 测试节点，host 或 host:port |
| `CFP_NODE1..4` | 空 | 自定义探测节点 |
| `CFP_IFACE` | 空 | 统计网卡，逗号分隔，留空自动 |
| `CFP_RESET_DAY` | `1` | 月流量重置日 1-31 |
| `CFP_CONN_MODE` | `auto` | 连接模式 `auto` / `http` |
| `CFP_PING_MODE` | `tcp` | Ping 模式 `tcp` / `icmp` |
| `CFP_DEBUG` | `0` | 调试日志 `0` / `1` |

---

## 节点输出

* 输出 sub.txt 节点文件，默认存放路径为 `.cache`
* 订阅：分配的域名/${SUB_PATH}；例如 `https://www.google.com/${SUB_PATH}`
* 非标端口订阅（游戏类）：分配的域名:端口/${SUB_PATH}，前缀不是 https，而是 http，例如 `http://www.google.com:1234/${SUB_PATH}`

---

## 二进制来源

* Docker 构建时：xray (`web`) / cloudflared (`bot`) 从 `{amd64|arm64}.oooen.com`（及备用源）下载固化到 `/opt/bin`；cf-probe 从 `huilang-me/cfsm-agent` 源码编译（版本 `9.9.9`）固化到 `/opt/bin/cfprobe`
* 非 Docker（PaaS / 玩具）：运行时自动下载，`web` / `bot` 走原项目 CDN，`cf-probe` 走 `huilang-me/cfsm-agent` 官方 Release（直连失败自动走 ghproxy 兜底）
* 运行时优先使用内置二进制（复制为随机名执行，约 90 秒后清理运行副本，进程不受影响）；无内置时才下载

### 自定义变量构建（fork 使用）

> 构建不会自动混淆：Dockerfile 直接使用仓库里的 `app.py`。自行注入密钥时，请在提交前处理 `app.py`（硬编后混淆或仅用私有仓库），否则明文会进入镜像。

**建议流程：**

1. 以 `app-src.py` 为干净源码，复制覆盖为 `app.py`
2. 将各变量默认值改成你的配置
3. （可选）对 `app.py` 做混淆后再提交
4. 推送触发 GitHub Actions，镜像推到 `ghcr.io/<你的用户名>/python-argo-cfsm:latest`

> fork 后首次需在仓库 Actions 页面手动启用 workflow。

---

## CF-Server-Monitor 面板

配合 [huilang-me/CF-Server-Monitor](https://github.com/huilang-me/CF-Server-Monitor) 使用：在面板添加服务器获取 `SERVER_ID / SECRET`，分别填入 `CFP_ID / CFP_SECRET`，Worker 地址填入 `CFP_URL`。

## License

MIT

---

# 免责声明

本程序仅供学习了解，非盈利目的，请于下载后 24 小时内删除，不得用作任何商业用途，文字、数据及图片均有所属版权，如转载须注明来源。
使用本程序必循遵守部署服务器所在地、所在国家和用户所在国家的法律法规，程序作者不对使用者任何不当行为负责。
