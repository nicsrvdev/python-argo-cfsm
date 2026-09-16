# Python-Argo-Cfsm

基于相关项目改造的 **Argo 隧道 + 多协议代理 + 服务器监控探针** Python 版。

保留：VLESS / VMess / Trojan 节点、Cloudflare Argo 固定/临时隧道、订阅生成与上传、Telegram 推送、Reality / Hysteria2 / Socks5 入站；探针使用 [CF-Server-Monitor](https://github.com/huilang-me/CF-Server-Monitor) 的 Go Probe（`cf-probe`，镜像内构建版本号 `9.9.9`）。

与 [nodejs 分支](https://github.com/nicsrvdev/nodejs-argo-cfsm) 变量名、探针配置格式、内置二进制策略对齐。

---

## 镜像

```bash
docker pull ghcr.io/nicsrvdev/python-argo-cfsm:latest
```

## 与运行时下载方案的差异

| 项目 | 纯运行时下载 | 本分支（对齐 nodejs） |
| --- | --- | --- |
| 探针 | 可选从 GitHub Release 下载 | **构建时源码编译** `cf-probe`（版本 9.9.9），运行时优先用内置 |
| xray / cloudflared | 运行时从 CDN 下载 | **构建时下载并固化** 到 `/opt/bin/{web,bot}` |
| 运行时 | 每次启动下载 | **有内置则复制随机名运行**；仅缺失时才下载 |
| 防检测 | 随机文件名 | 随机文件名 + 约 90s 清理运行副本（进程不受影响） |

源码文件：`app-src.py`（可读）；运行入口：`app.py`（默认可与源码相同；fork 硬编变量后可自行混淆再提交）。

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

非 Docker：上传 `app.py` + `requirements.txt`，`pip install -r requirements.txt` 后 `python3 app.py`，变量用环境变量注入。无内置二进制时会自动下载 `web` / `bot` / `cf-probe`。

---

## 环境变量

### 通用

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| UUID | 随机示例值 | 节点 UUID（三协议共用） |
| ARGO_AUTH | 空 | 固定隧道 token/json，留空=临时隧道 |
| ARGO_DOMAIN | 空 | 固定隧道域名，留空=临时隧道 |
| ARGO_PORT | 8001 | 隧道回源端口 |
| CFIP | saas.sin.fan | 节点优选域名/IP |
| CFPORT | 443 | 优选域名端口 |
| NAME | 空 | 节点名称前缀 |
| UPLOAD_URL | 空 | 订阅上传地址（Merge-sub 类） |
| PROJECT_URL | 空 | 项目分配 URL |
| AUTO_ACCESS | false | 自动访问保活（需同时填 PROJECT_URL） |
| S5_PORT / HY2_PORT / REALITY_PORT | 空 | 额外协议端口，填写即开启 |
| PORT | 3000 | 订阅 HTTP 服务端口 |
| SUB_PATH | sub | 订阅路径 |
| FILE_PATH | .cache | 运行目录 |
| CHAT_ID / BOT_TOKEN | 空 | Telegram 节点推送（两变量同填生效） |
| SHOW_LOG | true | 是否显示日志（`false` / `disable` / `no` 屏蔽） |

### 探针（CF-Server-Monitor）

`CFP_ID + CFP_SECRET + CFP_URL` **三者同时填写**才启动探针。

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| CFP_ID | 空 | 服务器 ID |
| CFP_SECRET | 空 | 服务器密钥 |
| CFP_URL | 空 | Worker 上报地址，如 `https://example.com/update` |
| CFP_INTERVAL | 60 | 上报间隔（秒） |
| CFP_COLLECT | 0 | 采样间隔（秒），`0`=WSS 自动采样 |
| CFP_CT / CFP_CU / CFP_CM / CFP_BD | 空 | 电信/联通/移动/BGP 测试节点 |
| CFP_NODE1..4 | 空 | 自定义探测节点 |
| CFP_IFACE | 空 | 统计网卡，逗号分隔 |
| CFP_RESET_DAY | 1 | 月流量重置日 |
| CFP_CONN_MODE | auto | `auto` / `http` |
| CFP_PING_MODE | tcp | `tcp` / `icmp` |
| CFP_DEBUG | 0 | 调试日志 `0` / `1` |

---

## 自定义变量构建（fork 使用）

> 构建不会自动混淆：Dockerfile 直接使用仓库里的 `app.py`。自行注入密钥时，请在提交前处理 `app.py`（硬编后混淆或仅用私有仓库），否则明文会进入镜像。

**建议流程：**

1. 以 `app-src.py` 为干净源码，复制覆盖为 `app.py`
2. 将各变量默认值改成你的配置
3. （可选）对 `app.py` 做混淆后再提交
4. 推送触发 GitHub Actions，镜像推到 `ghcr.io/<你的用户名>/python-argo-cfsm:latest`

> fork 后首次需在仓库 Actions 页面手动启用 workflow。

---

## 二进制来源（构建时）

- **xray (`web`) / cloudflared (`bot`)**：从 `{amd64|arm64}.oooen.com`（及备用源）下载并固化  
- **cf-probe**：构建时从 `huilang-me/cfsm-agent` 源码编译，版本 `9.9.9`

运行时：优先 `cp` 内置文件到 `FILE_PATH` 下随机名再执行；内置不存在时才按架构下载。

## CF-Server-Monitor 面板

配合 [huilang-me/CF-Server-Monitor](https://github.com/huilang-me/CF-Server-Monitor) 使用：面板 `SERVER_ID / SECRET` → 环境变量 `CFP_ID` / `CFP_SECRET`，Worker 地址 → `CFP_URL`。

## License

MIT
