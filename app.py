#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import json
import time
import base64
import random
import string
import shutil
import platform
import signal
import threading
import subprocess
import datetime
import requests
from pathlib import Path
from urllib.parse import urlparse, quote
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
# 注意：cryptography 只在 Reality / Hysteria2 需要时才懒加载（见
# generate_x25519_keypair / ensure_tls_certificates / get_certificate_fingerprint），
# 纯 Argo 部署不加载它，省约 20MB+ 常驻内存。

# =========================== 环境变量 ===========================
def _env_int(name, default, lo=1, hi=65535):
    """安全解析端口类环境变量：非法值回退默认值并告警，避免 import 期直接崩溃"""
    raw = os.environ.get(name, '')
    if raw in ('', None):
        return default
    try:
        value = int(str(raw).strip())
    except (ValueError, TypeError):
        sys.stdout.write(f'WARN: invalid {name}={raw!r}, using default {default}\n')
        sys.stdout.flush()
        return default
    if not (lo <= value <= hi):
        sys.stdout.write(f'WARN: {name}={value} out of range [{lo},{hi}], using default {default}\n')
        sys.stdout.flush()
        return default
    return value

UPLOAD_URL = os.environ.get('UPLOAD_URL', '')          # 节点或订阅上传地址
PROJECT_URL = os.environ.get('PROJECT_URL', '')        # 项目url,用于自动保活或上传订阅
AUTO_ACCESS = os.environ.get('AUTO_ACCESS', '').lower() == 'true'  # true开启自动保活,默认关闭
FILE_PATH = os.environ.get('FILE_PATH', '.cache')      # 运行目录,sub.txt保存路径
SUB_PATH = os.environ.get('SUB_PATH', 'sub')           # 订阅token
UUID = os.environ.get('UUID', '20e6e496-cf19-45c8-b883-14f5e11cd9f1')  # UUID
# ---------- CF 探针 (cfsm/cf-probe) 变量（与 nodejs 分支对齐） ----------
CFP_ID = os.environ.get('CFP_ID', '')                  # Server ID，必填
CFP_SECRET = os.environ.get('CFP_SECRET', '')          # 服务器密钥，必填
CFP_URL = os.environ.get('CFP_URL', '')                # Worker 上报地址，必填 例如 https://example.com/update
CFP_INTERVAL = os.environ.get('CFP_INTERVAL', '180')   # 上报间隔，秒（默认 180，省探针连接/采样开销；面板实时性要求高可改回 60）
CFP_COLLECT = os.environ.get('CFP_COLLECT', '0')       # 采样间隔，秒
CFP_CT = os.environ.get('CFP_CT', '')                  # 电信测试节点
CFP_CU = os.environ.get('CFP_CU', '')                  # 联通测试节点
CFP_CM = os.environ.get('CFP_CM', '')                  # 移动测试节点
CFP_BD = os.environ.get('CFP_BD', '')                  # BGP 测试节点
CFP_NODE1 = os.environ.get('CFP_NODE1', '')
CFP_NODE2 = os.environ.get('CFP_NODE2', '')
CFP_NODE3 = os.environ.get('CFP_NODE3', '')
CFP_NODE4 = os.environ.get('CFP_NODE4', '')
CFP_IFACE = os.environ.get('CFP_IFACE', '')            # 统计网卡,逗号分隔
CFP_RESET_DAY = os.environ.get('CFP_RESET_DAY', '1')   # 月流量重置日 1-31
CFP_CONN_MODE = os.environ.get('CFP_CONN_MODE', 'auto')# auto|http
CFP_PING_MODE = os.environ.get('CFP_PING_MODE', 'tcp') # tcp|icmp
CFP_DEBUG = os.environ.get('CFP_DEBUG', '0')           # 调试日志 0|1

# 镜像内内置二进制路径（构建时固化；运行时若存在则复制随机名，不存在才下载）
BUILTIN_XRAY = os.environ.get('BUILTIN_XRAY', '/opt/bin/web')
BUILTIN_BOT = os.environ.get('BUILTIN_BOT', '/opt/bin/bot')
BUILTIN_CFP = os.environ.get('BUILTIN_CFP', '/opt/bin/cfprobe')
# 可选：远程下载二进制时的 sha256 校验（留空不校验；内置二进制来自可信构建可不填）
XRAY_SHA256 = os.environ.get('XRAY_SHA256', '').lower()
CLOUDFLARED_SHA256 = os.environ.get('CLOUDFLARED_SHA256', '').lower()
CFPROBE_SHA256 = os.environ.get('CFPROBE_SHA256', '').lower()

ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', '')        # Argo固定隧道域名,留空使用临时隧道
ARGO_AUTH = os.environ.get('ARGO_AUTH', '')            # Argo固定隧道token或json,留空使用临时隧道
ARGO_PORT = _env_int('ARGO_PORT', 8001)   # Argo隧道端口
S5_PORT = os.environ.get('S5_PORT', '')                # socks5端口,留空不开启
HY2_PORT = os.environ.get('HY2_PORT', '')              # hy2端口,留空不开启
REALITY_PORT = os.environ.get('REALITY_PORT', '')      # reality端口,留空不开启
CFIP = os.environ.get('CFIP', 'saas.sin.fan')         # 优选ip或域名
CFPORT = _env_int('CFPORT', 443)          # 优选端口
NAME = os.environ.get('NAME', '')                      # 节点名称
CHAT_ID = os.environ.get('CHAT_ID', '')                # Telegram chat_id
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')            # Telegram bot_token
PORT = _env_int('PORT', 3000)           # http订阅端口
SHOW_LOG = os.environ.get('SHOW_LOG', 'true').lower() not in ('false', 'disable', 'no')  # 是否显示日志,默认显示，no/false/disable 不显示
WATCHDOG_ENABLED = os.environ.get('WATCHDOG_ENABLED', 'true').lower() not in ('false', 'disable', 'no')  # 看门狗：子进程死后自动拉起，默认开启
WATCHDOG_INTERVAL = _env_int('WATCHDOG_INTERVAL', 15, lo=5, hi=300)  # 看门狗巡检间隔，秒

# =========================== 日志控制 ===========================
def log(msg):
    if SHOW_LOG:
        print(msg)

def log_error(msg):
    if SHOW_LOG:
        print(msg, file=sys.stderr)

def always_log(msg):
    sys.stdout.write(msg + '\n')
    sys.stdout.flush()

# =========================== 全局变量 ===========================
private_key = ''
public_key = ''
sub_txt_content = ''
FILE_PATH = Path(FILE_PATH).resolve()

def generate_random_name(length=6):
    return ''.join(random.choices(string.ascii_lowercase, k=length))

web_name = generate_random_name()
bot_name = generate_random_name()
cf_probe_name = generate_random_name()  # CF探针二进制随机文件名(防检测)

web_path = FILE_PATH / web_name
bot_path = FILE_PATH / bot_name
cf_probe_path = FILE_PATH / cf_probe_name
sub_path = FILE_PATH / 'sub.txt'
list_path = FILE_PATH / 'list.txt'
boot_log_path = FILE_PATH / 'boot.log'
config_path = FILE_PATH / 'config.json'
cf_probe_config_path = FILE_PATH / 'cfprobe.conf'  # cf-probe run -config 格式(KEY=VALUE)
cert_path = FILE_PATH / 'cert.pem'
key_path = FILE_PATH / 'private.key'

# =========================== 端口检查 ===========================
def is_valid_port(port):
    try:
        if port is None or port == '':
            return False
        port_num = int(port)
        if port_num < 1 or port_num > 65535:
            return False
        return True
    except (ValueError, TypeError):
        return False

# =========================== X25519 密钥对生成 ===========================
def generate_x25519_keypair():
    """使用 cryptography 库生成 X25519 密钥对,返回 base64url 编码的私钥和公钥"""
    from cryptography.hazmat.primitives.asymmetric import x25519
    from cryptography.hazmat.primitives import serialization
    priv = x25519.X25519PrivateKey.generate()
    pub = priv.public_key()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    pub_bytes = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    return {
        'privateKey': base64.urlsafe_b64encode(priv_bytes).decode().rstrip('='),
        'publicKey': base64.urlsafe_b64encode(pub_bytes).decode().rstrip('=')
    }

def generate_or_load_keypair():
    """生成或加载 X25519 密钥对"""
    global private_key, public_key
    key_file_path = FILE_PATH / 'key.txt'
    if key_file_path.exists():
        content = key_file_path.read_text(encoding='utf-8')
        priv_match = re.search(r'PrivateKey:\s*(.*)', content)
        pub_match = re.search(r'PublicKey:\s*(.*)', content)
        if priv_match and pub_match:
            private_key = priv_match.group(1).strip()
            public_key = pub_match.group(1).strip()
            log(f'Public Key: {public_key}')
            return
    keypair = generate_x25519_keypair()
    private_key = keypair['privateKey']
    public_key = keypair['publicKey']
    key_file_path.write_text(
        f'PrivateKey: {private_key}\nPublicKey: {public_key}\n', encoding='utf-8')
    log(f'Public Key: {public_key}')

# =========================== TLS 证书生成 ===========================
def ensure_tls_certificates(cert_file, key_file):
    """生成自签名 TLS 证书 (用于 Hysteria2)；失败时抛错，由调用方降级处理"""
    if cert_file.exists() and key_file.exists():
        return
    cert_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        ec_private_key = ec.generate_private_key(ec.SECP256R1())
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, 'bing.com')
        ])
        cert_obj = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(ec_private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None))
            .not_valid_after((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)).replace(tzinfo=None))
            .sign(ec_private_key, hashes.SHA256())
        )
        key_pem = ec_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        cert_pem = cert_obj.public_bytes(serialization.Encoding.PEM)
        key_file.write_bytes(key_pem)
        cert_file.write_bytes(cert_pem)
    except Exception as e:
        # 不再使用硬编码私钥做 fallback：所有走 fallback 的实例会共用同一套证书私钥。
        # 抛错让调用方决定降级策略（start_server 会禁用 Hysteria2 并继续运行）。
        log_error(f'Failed to generate TLS certificate: {e}')
        raise

# =========================== 证书指纹计算 ===========================
def get_certificate_fingerprint(cert_file):
    """计算证书的 SHA-256 指纹,优先用 openssl,不可用时用 cryptography 兜底"""
    try:
        result = subprocess.run(
            ['openssl', 'x509', '-noout', '-fingerprint', '-sha256', '-in', str(cert_file)],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            match = re.search(r'=(.+)$', output)
            if match and match.group(1):
                return match.group(1).upper()
    except Exception:
        pass
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes
        with open(cert_file, 'rb') as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data)
        fingerprint = cert.fingerprint(hashes.SHA256())
        return ':'.join(f'{b:02X}' for b in fingerprint)
    except Exception as e:
        log_error(f'Failed to calculate certificate fingerprint: {e}')
        return ''

# =========================== 创建运行文件夹 ===========================
def create_directory():
    if not SHOW_LOG:
        print('\033c', end='')
    FILE_PATH.mkdir(parents=True, exist_ok=True)
    # log(f'{FILE_PATH} is ready')

# =========================== 删除旧节点 ===========================
def delete_nodes():
    try:
        if not UPLOAD_URL:
            return
        if not sub_path.exists():
            return
        content = sub_path.read_text(encoding='utf-8')
        decoded = base64.b64decode(content).decode('utf-8')
        nodes = [line for line in decoded.split('\n')
                 if re.match(r'(vless|vmess|trojan|hysteria2|socks)://', line)]
        if not nodes:
            return
        requests.post(f'{UPLOAD_URL}/api/delete-nodes',
                       json={'nodes': nodes}, timeout=10)
    except Exception:
        pass

# =========================== 清理历史文件 ===========================
def cleanup_old_files():
    """清理 FILE_PATH 目录下的所有文件, 保留 key.txt/cert.pem/private.key"""
    # key.txt: Reality 密钥对, cert.pem/private.key: Hysteria2 证书, 删除后重启指纹变化导致节点失效
    preserve_files = {FILE_PATH / 'key.txt', cert_path, key_path}
    try:
        for item in FILE_PATH.iterdir():
            if item in preserve_files:
                continue
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception:
                pass
    except Exception:
        pass

# =========================== 判断系统架构 ===========================
def get_system_architecture():
    arch = platform.machine().lower()
    if arch in ('arm', 'arm64', 'aarch64'):
        return 'arm'
    return 'amd'

# =========================== 下载文件 ===========================
def _verify_sha256(file_path, expected):
    """校验文件 sha256；expected 为空表示不校验"""
    if not expected:
        return True
    import hashlib
    digest = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            digest.update(chunk)
    actual = digest.hexdigest().lower()
    if actual != expected.lower():
        log_error(f'sha256 mismatch for {file_path.name}: expected {expected}, got {actual}')
        return False
    log(f'sha256 verified: {file_path.name}')
    return True


def download_file(file_name, file_url, sha256=''):
    file_path = FILE_PATH / file_name
    try:
        response = requests.get(file_url, stream=True, timeout=180)
        response.raise_for_status()
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if not _verify_sha256(file_path, sha256):
            try:
                file_path.unlink()
            except FileNotFoundError:
                pass
            return False
        log(f'Download {file_name} successfully')
        return True
    except Exception as e:
        log_error(f'Download {file_name} failed: {e}')
        try:
            file_path.unlink()
        except FileNotFoundError:
            pass
        return False


# =========================== 内置二进制 / 下载兜底 ===========================
def _copy_builtin(src_path, dst_path):
    src_p = Path(src_path)
    if not src_p.is_file():
        return False
    try:
        shutil.copy2(str(src_p), str(dst_path))
        os.chmod(str(dst_path), 0o775)
        log(f'builtin {src_p.name} -> {dst_path.name}')
        return True
    except Exception as e:
        log_error(f'copy builtin failed {src_path}: {e}')
        return False


def prepare_or_download_binaries():
    """优先使用镜像内置三二进制（复制为随机名）；缺失才远程下载。"""
    architecture = get_system_architecture()
    if architecture == 'arm':
        base_urls = ['https://arm64.oooen.com', 'https://arm64.ssss.nyc.mn']
        cf_arch = 'arm64'
    else:
        base_urls = ['https://amd64.oooen.com', 'https://amd64.ssss.nyc.mn']
        cf_arch = 'amd64'

    if not _copy_builtin(BUILTIN_XRAY, web_path):
        downloaded = False
        for index, base_url in enumerate(base_urls):
            if download_file(web_name, f'{base_url}/web', XRAY_SHA256):
                downloaded = True
                break
            if index + 1 < len(base_urls):
                log(f'Retrying {web_name} from backup source')
        if not downloaded:
            log_error('Error preparing web binary: builtin missing and download failed')
        elif web_path.exists():
            os.chmod(str(web_path), 0o775)

    if not _copy_builtin(BUILTIN_BOT, bot_path):
        downloaded = False
        for index, base_url in enumerate(base_urls):
            if download_file(bot_name, f'{base_url}/bot', CLOUDFLARED_SHA256):
                downloaded = True
                break
            if index + 1 < len(base_urls):
                log(f'Retrying {bot_name} from backup source')
        if not downloaded:
            log_error('Error preparing bot binary: builtin missing and download failed')
        elif bot_path.exists():
            os.chmod(str(bot_path), 0o775)

    need_cfp = bool(CFP_ID and CFP_SECRET and CFP_URL)
    if need_cfp:
        if not _copy_builtin(BUILTIN_CFP, cf_probe_path):
            asset = f'cf-probe-linux-{cf_arch}'
            cf_urls = [
                f'https://github.com/huilang-me/cfsm-agent/releases/latest/download/{asset}',
                f'https://ghproxy.net/https://github.com/huilang-me/cfsm-agent/releases/latest/download/{asset}',
                f'https://mirror.ghproxy.com/https://github.com/huilang-me/cfsm-agent/releases/latest/download/{asset}',
            ]
            downloaded = False
            for url in cf_urls:
                if download_file(cf_probe_name, url, CFPROBE_SHA256):
                    downloaded = True
                    break
            if not downloaded:
                log_error('Error preparing cf-probe: builtin missing and download failed')
            elif cf_probe_path.exists():
                os.chmod(str(cf_probe_path), 0o775)
    else:
        log('CFP_ID/CFP_SECRET/CFP_URL not all set, skip cf-probe')


def live_binary(runtime_path, builtin_path):
    """运行副本被清理后回退到内置路径。"""
    p = Path(runtime_path)
    if p.is_file():
        return str(p)
    b = Path(builtin_path)
    if b.is_file():
        return str(b)
    return str(p)


# =========================== Argo 隧道配置 ===========================
def argo_type():
    if not ARGO_AUTH or not ARGO_DOMAIN:
        log('ARGO_DOMAIN or ARGO_AUTH variable is empty, use quick tunnels')
        return

    if 'TunnelSecret' in ARGO_AUTH:
        (FILE_PATH / 'tunnel.json').write_text(ARGO_AUTH, encoding='utf-8')
        try:
            tunnel_id = json.loads(ARGO_AUTH).get('TunnelID') or ''
        except Exception as e:
            log_error(f'ARGO_AUTH JSON 解析失败，请检查 TunnelID 字段: {e}')
            return
        if not tunnel_id:
            log_error('ARGO_AUTH JSON 中缺少 TunnelID，已跳过固定隧道配置')
            return
        tunnel_yaml = f"""
tunnel: {tunnel_id}
credentials-file: {FILE_PATH / 'tunnel.json'}
protocol: http2

ingress:
  - hostname: {ARGO_DOMAIN}
    service: http://localhost:{ARGO_PORT}
    originRequest:
      noTLSVerify: true
  - service: http_status:404
"""
        (FILE_PATH / 'tunnel.yml').write_text(tunnel_yaml, encoding='utf-8')
    else:
        log(f'Using token connect to tunnel, please set {ARGO_PORT} in cloudflare')

# =========================== CF探针配置生成 ===========================
def generate_cf_probe_config():
    """写入 cf-probe 配置文件(cfsm run -config 格式,KEY=VALUE),三参必填"""
    if not CFP_ID or not CFP_SECRET or not CFP_URL:
        return
    cf_conf = (
        f'SERVER_ID="{CFP_ID}"\n'
        f'SECRET="{CFP_SECRET}"\n'
        f'WORKER_URL="{CFP_URL}"\n'
        f'COLLECT_INTERVAL="{CFP_COLLECT}"\n'
        f'REPORT_INTERVAL="{CFP_INTERVAL}"\n'
        f'CT_NODE="{CFP_CT}"\n'
        f'CU_NODE="{CFP_CU}"\n'
        f'CM_NODE="{CFP_CM}"\n'
        f'BD_NODE="{CFP_BD}"\n'
        f'NODE_1="{CFP_NODE1}"\n'
        f'NODE_2="{CFP_NODE2}"\n'
        f'NODE_3="{CFP_NODE3}"\n'
        f'NODE_4="{CFP_NODE4}"\n'
        f'INTERFACE="{CFP_IFACE}"\n'
        f'RESET_DAY="{CFP_RESET_DAY}"\n'
        f'CONNECTION_MODE="{CFP_CONN_MODE}"\n'
        f'PING_MODE="{CFP_PING_MODE}"\n'
        f'AUTO_UPDATE="0"\n'
        f'CONFIG_MD5="none"\n'
    )
    cf_probe_config_path.write_text(cf_conf, encoding='utf-8')
    log(f'cf-probe config saved: {cf_probe_config_path}')

# =========================== Xray 配置生成 ===========================
def generate_xray_config():
    config = {
        "log": {
            "access": "/dev/null",
            "error": "/dev/null",
            "loglevel": "none"
        },
        "inbounds": [
            {
                "tag": "vless-fallback-in",
                "listen": "::",
                "port": ARGO_PORT,
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": UUID, "flow": "xtls-rprx-vision"}],
                    "decryption": "none",
                    "fallbacks": [
                        {"dest": 51001},
                        {"path": "/vless-argo", "dest": 51002},
                        {"path": "/vmess-argo", "dest": 51003},
                        {"path": "/trojan-argo", "dest": 51004}
                    ]
                },
                "streamSettings": {"network": "tcp"}
            },
            {
                "tag": "vless-tcp-in",
                "port": 51001,
                "listen": "127.0.0.1",
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": UUID}],
                    "decryption": "none"
                },
                "streamSettings": {"network": "tcp", "security": "none"}
            },
            {
                "tag": "vless-ws-in",
                "port": 51002,
                "listen": "127.0.0.1",
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": UUID, "level": 0}],
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "none",
                    "wsSettings": {"path": "/vless-argo"}
                }
            },
            {
                "tag": "vmess-ws-in",
                "port": 51003,
                "listen": "127.0.0.1",
                "protocol": "vmess",
                "settings": {
                    "clients": [{"id": UUID, "alterId": 0}]
                },
                "streamSettings": {
                    "network": "ws",
                    "wsSettings": {"path": "/vmess-argo"}
                }
            },
            {
                "tag": "trojan-ws-in",
                "port": 51004,
                "listen": "127.0.0.1",
                "protocol": "trojan",
                "settings": {
                    "clients": [{"password": UUID}]
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "none",
                    "wsSettings": {"path": "/trojan-argo"}
                }
            }
        ],
        "dns": {"servers": ["https+local://8.8.8.8/dns-query"]},
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"}
        ]
    }

    # VLESS Reality 配置
    if is_valid_port(REALITY_PORT):
        config["inbounds"].append({
            "tag": "vless-reality-in",
            "listen": "::",
            "port": int(REALITY_PORT),
            "protocol": "vless",
            "settings": {
                "clients": [{"id": UUID, "flow": "xtls-rprx-vision"}],
                "decryption": "none"
            },
            "streamSettings": {
                "network": "raw",
                "security": "reality",
                "realitySettings": {
                    "show": False,
                    "dest": "www.iij.ad.jp:443",
                    "xver": 0,
                    "serverNames": ["www.iij.ad.jp"],
                    "privateKey": private_key,
                    "shortIds": [""]
                }
            }
        })

    # Hysteria2 配置
    if is_valid_port(HY2_PORT):
        config["inbounds"].append({
            "tag": "hysteria-in",
            "listen": "::",
            "port": int(HY2_PORT),
            "protocol": "hysteria",
            "settings": {
                "version": 2,
                "clients": [{"auth": UUID}]
            },
            "streamSettings": {
                "network": "hysteria",
                "hysteriaSettings": {
                    "version": 2,
                    "masquerade": {"type": "proxy", "url": "https://bing.com"}
                },
                "security": "tls",
                "tlsSettings": {
                    "alpn": ["h3"],
                    "certificates": [
                        {
                            "certificateFile": str(cert_path),
                            "keyFile": str(key_path)
                        }
                    ]
                }
            }
        })

    # SOCKS5 配置
    if is_valid_port(S5_PORT):
        config["inbounds"].append({
            "tag": "s5-in",
            "listen": "::",
            "port": int(S5_PORT),
            "protocol": "socks",
            "settings": {
                "auth": "password",
                "accounts": [{"user": UUID[:8], "pass": UUID[-12:]}],
                "udp": True
            }
        })

    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')

# =========================== 进程启动（无 shell，防命令注入） ===========================
def run_daemon(argv, log_path=None):
    """以后台守护进程方式启动程序，返回 Popen 对象（失败返回 None）。

    argv 为参数列表（不经过 shell），天然免疫命令注入；
    start_new_session + DEVNULL 实现 nohup 语义，父进程退出不影响子进程。
    注意：返回的 Popen 对象必须由调用方保存（见 _start_child），丢掉它
    就没人知道子进程死活——这就是以前子进程被杀后不自动拉起的根因。
    """
    log_file = None
    try:
        if log_path:
            log_file = open(str(log_path), 'ab')
            out = log_file
            err = subprocess.STDOUT
        else:
            out = subprocess.DEVNULL
            err = subprocess.DEVNULL
        proc = subprocess.Popen(
            [str(a) for a in argv],
            stdin=subprocess.DEVNULL,
            stdout=out, stderr=err,
            start_new_session=True, close_fds=True,
        )
        proc._log_file = log_file
        return proc
    except Exception as e:
        if log_file is not None:
            try:
                log_file.close()
            except Exception:
                pass
        log_error(f'Failed to start daemon {argv[0] if argv else "?"}: {e}')
        return None


def pkill_match(pattern):
    """按命令行特征结束进程（列表形式调用 pkill，不经过 shell）"""
    try:
        subprocess.run(['pkill', '-f', pattern],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=10)
    except Exception:
        pass


# =========================== 子进程跟踪 + 看门狗 ===========================
# _children: name -> {'proc': Popen, 'argv': [...], 'started_at': float}
# name 只有三个：'xray' / 'cloudflared' / 'cfprobe'。看门狗每
# WATCHDOG_INTERVAL 秒 poll() 一次，死了按指数退避重启（5s/10s/20s/40s/60s封顶，
# 配置坏了也不会 tight loop 刷屏）；连续存活 60 秒以上清零失败计数。
_children = {}
_children_lock = threading.Lock()
_shutdown_event = threading.Event()
_watchdog_started = False
_watchdog_failures = {}

_CHILD_PATTERNS = {'xray': web_name, 'cloudflared': bot_name,
                   'cfprobe': cf_probe_name}  # name -> pkill 用的随机文件名


def _child_pattern(name):
    return _CHILD_PATTERNS.get(name, '')


def _start_child(name, argv, log_path=None):
    """启动并登记一个子进程，返回 Popen（失败返回 None）。"""
    proc = run_daemon(argv, log_path=log_path)
    if proc is None:
        return None
    with _children_lock:
        _children[name] = {'proc': proc, 'argv': [str(a) for a in argv],
                           'started_at': time.monotonic()}
    return proc


def _stop_child(name):
    """优雅停一个已登记的子进程（terminate → 5s 超时 kill），再 pkill 兜底清孤儿。"""
    with _children_lock:
        record = _children.get(name)
    proc = record['proc'] if record else None
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    log_file = getattr(proc, '_log_file', None) if proc is not None else None
    if log_file is not None:
        try:
            log_file.close()
        except Exception:
            pass
    pattern = _child_pattern(name)
    if pattern:
        pkill_match(pattern)


def _resolve_argv(argv):
    """重启时把已被 90 秒清理删掉的运行副本路径换回内置二进制。

    clean_files() 会删 .cache/<随机名> 三个副本，进程本身不受影响，但按原
    argv 重启会 FileNotFoundError；live_binary() 在副本没了时回退 /opt/bin。
    """
    if not argv:
        return argv
    resolved = list(argv)
    runtime_to_builtin = {
        str(web_path): BUILTIN_XRAY,
        str(bot_path): BUILTIN_BOT,
        str(cf_probe_path): BUILTIN_CFP,
    }
    builtin = runtime_to_builtin.get(str(resolved[0]))
    if builtin:
        resolved[0] = live_binary(resolved[0], builtin)
    return resolved


def _cloudflared_argv():
    """构造 cloudflared 启动参数，返回 (argv, is_temp_tunnel)。"""
    bot_bin = live_binary(bot_path, BUILTIN_BOT)
    auth = ARGO_AUTH or ''
    if re.match(r'^[A-Z0-9a-z=]{120,250}$', auth):
        return ([bot_bin, 'tunnel', '--edge-ip-version', 'auto', '--no-autoupdate',
                 '--protocol', 'http2', 'run', '--token', auth], False)
    if 'TunnelSecret' in auth:
        return ([bot_bin, 'tunnel', '--edge-ip-version', 'auto',
                 '--config', str(FILE_PATH / 'tunnel.yml'), 'run'], False)
    if auth:
        log_error('ARGO_AUTH 格式无法识别（既不是 token 也不是 TunnelSecret JSON），已降级为临时隧道')
    return ([bot_bin, 'tunnel', '--edge-ip-version', 'auto', '--no-autoupdate',
             '--protocol', 'http2', '--logfile', str(boot_log_path),
             '--loglevel', 'info', '--url', f'http://localhost:{ARGO_PORT}'], True)


def _wait_temp_domain(timeout=30):
    """等 cloudflared 把临时域名写进 boot.log，返回域名或 None。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if boot_log_path.exists():
                found = re.findall(
                    r'https?://([^ ]*trycloudflare\.com)/?',
                    boot_log_path.read_text(encoding='utf-8'))
                if found:
                    return found[0]
        except Exception:
            pass
        time.sleep(1)
    return None


def _restart_child(name):
    """拉起一个已死的子进程。返回 True 表示进程已起来（临时隧道还需域名就绪）。"""
    with _children_lock:
        record = _children.get(name)
    if not record:
        return False
    argv = _resolve_argv(record['argv'])
    if name == 'xray' and not config_path.exists():
        generate_xray_config()
    elif name == 'cfprobe' and not cf_probe_config_path.exists():
        generate_cf_probe_config()
    elif name == 'cloudflared' and 'TunnelSecret' in (ARGO_AUTH or ''):
        if not (FILE_PATH / 'tunnel.yml').exists():
            argo_type()
    if name == 'cloudflared' and '--url' in argv:
        # 临时隧道（--url 形式）：旧 boot.log 里是过期域名，必须清掉再起，否则会误用旧域名
        try:
            boot_log_path.unlink(missing_ok=True)
        except Exception:
            pass
    proc = _start_child(name, argv)
    if proc is None:
        log_error(f'watchdog: failed to restart {name}')
        return False
    log(f'watchdog: {name} restarted (pid {proc.pid})')
    if name == 'cloudflared':
        _argv, is_temp = _cloudflared_argv()
        if is_temp:
            domain = _wait_temp_domain()
            if domain:
                log(f'watchdog: new ArgoDomain: {domain}')
                generate_links(domain)
                return True
            log_error('watchdog: cloudflared restarted but no new temp domain yet; will retry next cycle')
            return False
    return True


def _watchdog_loop():
    while not _shutdown_event.is_set():
        if _shutdown_event.wait(WATCHDOG_INTERVAL):
            break
        with _children_lock:
            items = list(_children.items())
        for name, record in items:
            if _shutdown_event.is_set():
                break
            proc = record['proc']
            if proc is None or proc.poll() is None:
                if proc is not None and time.monotonic() - record.get('started_at', 0) > 60:
                    _watchdog_failures[name] = 0
                continue
            failures = _watchdog_failures.get(name, 0) + 1
            _watchdog_failures[name] = failures
            delay = min(60, 5 * (2 ** (failures - 1)))
            log_error(f'watchdog: {name} exited (code {proc.returncode}), restart #{failures} in {delay}s')
            if _shutdown_event.wait(delay):
                break
            try:
                _restart_child(name)
            except Exception as e:
                log_error(f'watchdog: restart {name} failed: {e}')


def _start_watchdog():
    """在节点生成完成后启动看门狗（只启动一次）。"""
    global _watchdog_started
    if not WATCHDOG_ENABLED or _watchdog_started:
        return
    _watchdog_started = True
    t = threading.Thread(target=_watchdog_loop, daemon=True)
    t.start()
    log(f'watchdog started (interval {WATCHDOG_INTERVAL}s)')

# =========================== 下载并运行 ===========================
def download_files_and_run():
    # 内置二进制优先：复制随机名；没有才下载
    prepare_or_download_binaries()
    architecture = get_system_architecture()
    log(f'architecture: {architecture}, binaries prepared')

    # 生成并运行 CF 探针 (cf-probe)：配置由 generate_cf_probe_config() 统一生成
    if CFP_ID and CFP_SECRET and CFP_URL:
        generate_cf_probe_config()
        debug_arg = '-debug=1' if CFP_DEBUG == '1' else '-debug=0'
        cfp_bin = live_binary(cf_probe_path, BUILTIN_CFP)
        if _start_child('cfprobe', [cfp_bin, 'run', '-config', str(cf_probe_config_path), debug_arg]):
            log(f'{cf_probe_name} (cf-probe) is running')
            time.sleep(1)
    else:
        log('CFP_ID/CFP_SECRET/CFP_URL not all set, skip running probe')

    # 运行 Xray
    web_bin = live_binary(web_path, BUILTIN_XRAY)
    if _start_child('xray', [web_bin, '-c', str(config_path)]):
        log(f'{web_name} is running')
        time.sleep(1)

    # 运行 Cloudflared（参数列表形式传递，ARGO_AUTH 不经过 shell，无注入风险）
    bot_bin = live_binary(bot_path, BUILTIN_BOT)
    if Path(bot_bin).is_file():
        argv, _is_temp = _cloudflared_argv()
        if _start_child('cloudflared', argv):
            log(f'{bot_name} is running')
            time.sleep(2)

    time.sleep(5)


# =========================== 提取隧道域名 ===========================
def extract_domains(max_retries=5):
    """提取 Argo 隧道域名。

    固定隧道直接使用 ARGO_DOMAIN；临时隧道从 cloudflared 日志解析，
    最多重试 max_retries 次（原递归无上限，会在网络持续异常时无限循环）。
    全部失败时仍生成非 Argo 节点（Hysteria2/Reality/Socks5），不整体崩溃。
    """
    if ARGO_AUTH and ARGO_DOMAIN:
        log(f'ARGO_DOMAIN: {ARGO_DOMAIN}')
        generate_links(ARGO_DOMAIN)
        return

    argo_domain = None
    for attempt in range(1, max_retries + 1):
        try:
            if boot_log_path.exists():
                found = re.findall(
                    r'https?://([^ ]*trycloudflare\.com)/?',
                    boot_log_path.read_text(encoding='utf-8'))
                if found:
                    argo_domain = found[0]
                    break
        except Exception as e:
            log_error(f'Error reading boot.log: {e}')
        if attempt < max_retries:
            log(f'ArgoDomain not found (attempt {attempt}/{max_retries}), re-running bot')
            try:
                boot_log_path.unlink(missing_ok=True)
            except Exception:
                pass
            # 经 _stop_child/_start_child 重启，登记在 _children 里，看门狗才能接着管它
            _stop_child('cloudflared')
            time.sleep(3)
            argv, _is_temp = _cloudflared_argv()
            if _start_child('cloudflared', argv):
                log(f'{bot_name} is running')
            time.sleep(6)

    if argo_domain:
        log(f'ArgoDomain: {argo_domain}')
        generate_links(argo_domain)
    else:
        log_error(f'ArgoDomain not found after {max_retries} attempts; continuing without argo nodes')
        generate_links(None)

# =========================== 获取 ISP 信息 ===========================
def get_meta_info():
    try:
        resp = requests.get('https://api.ip.sb/geoip',
                            headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        data = resp.json()
        if data.get('country_code') and data.get('isp'):
            return f"{data['country_code']}-{data['isp']}".replace(' ', '_')
    except Exception:
        pass
    try:
        resp = requests.get('http://ip-api.com/json',
                            headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        data = resp.json()
        if data.get('status') == 'success' and data.get('countryCode') and data.get('org'):
            return f"{data['countryCode']}-{data['org']}".replace(' ', '_')
    except Exception:
        pass
    return 'Unknown'

# =========================== 获取服务器公网 IP ===========================
def get_server_ip():
    server_ip = ''
    try:
        resp = requests.get('http://ipv4.ip.sb', timeout=3)
        server_ip = resp.text.strip()
    except Exception:
        try:
            result = subprocess.run(['curl', '-sm', '3', 'ipv4.ip.sb'],
                                    capture_output=True, text=True, timeout=5)
            server_ip = result.stdout.strip()
        except Exception:
            try:
                resp = requests.get('http://ipv6.ip.sb', timeout=3)
                server_ip = f'[{resp.text.strip()}]'
            except Exception:
                try:
                    result = subprocess.run(['curl', '-sm', '3', 'ipv6.ip.sb'],
                                            capture_output=True, text=True, timeout=5)
                    server_ip = f'[{result.stdout.strip()}]'
                except Exception as e:
                    log_error(f'Failed to get IP address: {e}')
    return server_ip

# =========================== 生成节点链接 ===========================
def generate_links(argo_domain):
    global sub_txt_content

    isp = get_meta_info()
    node_name = f'{NAME}-{isp}' if NAME else isp
    # 节点名出现在 URL fragment 中，中文/空格需编码，否则部分客户端解析异常
    node_name_enc = quote(node_name, safe='')
    server_ip = get_server_ip()

    time.sleep(2)

    sub_txt = ''

    # Argo 节点 (VLESS / VMess / Trojan)
    if argo_domain:
        sub_txt += f'\nvless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={argo_domain}&fp=firefox&type=ws&host={argo_domain}&path=%2Fvless-argo%3Fed%3D2560#{node_name_enc}'

        vmess_obj = {
            'v': '2', 'ps': node_name, 'add': CFIP, 'port': CFPORT,
            'id': UUID, 'aid': '0', 'scy': 'auto', 'net': 'ws',
            'type': 'none', 'host': argo_domain, 'path': '/vmess-argo?ed=2560',
            'tls': 'tls', 'sni': argo_domain, 'alpn': '', 'fp': 'firefox'
        }
        vmess_b64 = base64.b64encode(json.dumps(vmess_obj, separators=(',', ':')).encode()).decode()
        sub_txt += f'\nvmess://{vmess_b64}'

        sub_txt += f'\ntrojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={argo_domain}&fp=firefox&type=ws&host={argo_domain}&path=%2Ftrojan-argo%3Fed%3D2560#{node_name_enc}'

    # Hysteria2 节点
    if is_valid_port(HY2_PORT):
        fingerprint = get_certificate_fingerprint(cert_path)
        fingerprint_param = f'&pinSHA256={quote(fingerprint, safe="")}' if fingerprint else ''
        sub_txt += f'\nhysteria2://{UUID}@{server_ip}:{HY2_PORT}/?sni=www.bing.com&insecure=0&alpn=h3&obfs=none{fingerprint_param}#{node_name_enc}'

    # Reality 节点
    if is_valid_port(REALITY_PORT):
        sub_txt += f'\nvless://{UUID}@{server_ip}:{REALITY_PORT}?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.iij.ad.jp&fp=firefox&pbk={public_key}&type=tcp&headerType=none#{node_name_enc}'

    # SOCKS5 节点
    if is_valid_port(S5_PORT):
        s5_auth = base64.b64encode(f'{UUID[:8]}:{UUID[-12:]}'.encode()).decode()
        sub_txt += f'\nsocks://{s5_auth}@{server_ip}:{S5_PORT}#{node_name_enc}'

    sub_txt_b64 = base64.b64encode(sub_txt.encode()).decode()
    if SHOW_LOG:
        print(f'\033[32m{sub_txt_b64}\033[0m')
        print(f'\033[35mLogs will be deleted in 90 seconds, you can copy the above nodes\033[0m')

    sub_path.write_text(sub_txt_b64, encoding='utf-8')
    list_path.write_text(sub_txt, encoding='utf-8')
    log(f'{FILE_PATH}/sub.txt saved successfully')

    sub_txt_content = sub_txt_b64
    return sub_txt

# =========================== Telegram 推送 ===========================
def send_telegram():
    if not BOT_TOKEN or not CHAT_ID:
        log('TG variables is empty, Skipping push nodes to TG')
        return
    try:
        message = sub_path.read_text(encoding='utf-8')
        url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
        escaped_name = re.sub(r'[_*\[\]()~`>#+=|{}.!-]', r'\\\g<0>', NAME)
        params = {
            'chat_id': CHAT_ID,
            'text': f'**{escaped_name}节点推送通知**\n```{message}```',
            'parse_mode': 'MarkdownV2'
        }
        requests.post(url, params=params, timeout=10)
        log('Telegram message sent successfully')
    except Exception as e:
        log_error(f'Failed to send Telegram message: {e}')

# =========================== 上传节点到订阅器 ===========================
def upload_nodes():
    if UPLOAD_URL and PROJECT_URL:
        subscription_url = f'{PROJECT_URL}/{SUB_PATH}'
        try:
            resp = requests.post(f'{UPLOAD_URL}/api/add-subscriptions',
                                 json={'subscription': [subscription_url]},
                                 timeout=10)
            if resp.status_code == 200:
                log('Subscription uploaded successfully')
        except Exception:
            pass
    elif UPLOAD_URL:
        if not list_path.exists():
            return
        content = list_path.read_text(encoding='utf-8')
        nodes = [line for line in content.split('\n')
                 if re.match(r'(vless|vmess|trojan|hysteria2|socks)://', line)]
        if not nodes:
            return
        try:
            resp = requests.post(f'{UPLOAD_URL}/api/add-nodes',
                                 json={'nodes': nodes},
                                 timeout=10)
            if resp.status_code == 200:
                log('Nodes uploaded successfully')
        except Exception:
            pass

# =========================== 自动保活 ===========================
def add_visit_task():
    if not AUTO_ACCESS or not PROJECT_URL:
        log('Skipping adding automatic access task')
        return
    try:
        requests.post('https://oooo.serv00.net/add-url',
                      json={'url': PROJECT_URL},
                      headers={'Content-Type': 'application/json'},
                      timeout=10)
        log('automatic access task added successfully')
    except Exception as e:
        log_error(f'Add URL failed: {e}')

# =========================== 文件清理 ===========================
def clean_files():
    def cleanup():
        time.sleep(90)
        # 注意: key.txt/cert.pem/private.key 不能删除, 删除后重启会导致 Reality 公钥和 Hysteria2 证书指纹变化, 节点失效
        # 同理 config.json / cfprobe.conf / tunnel.json / tunnel.yml 也不能删：
        # 看门狗重启 xray / cf-probe / 固定隧道要靠它们；删了重启就起不来。
        # 二进制副本（web/bot/cfprobe 运行副本）可以删，重启时 _resolve_argv() 会回退到 /opt/bin。
        files_to_delete = [boot_log_path, list_path,
                           web_path, bot_path, cf_probe_path]

        for f in files_to_delete:
            try:
                f.unlink()
            except FileNotFoundError:
                pass

        if SHOW_LOG:
            os.system('clear' if os.name == 'posix' else 'cls')
        always_log('App is running')
        log('Thank you for using this script, enjoy!')

    t = threading.Thread(target=cleanup, daemon=True)
    t.start()

# =========================== HTTP 服务 ===========================
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == f'/{SUB_PATH}':
            if not sub_txt_content:
                # 节点尚未生成（启动后约十几秒空窗期），返回 503 而不是空订阅
                self.send_response(503)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Retry-After', '10')
                self.end_headers()
                self.wfile.write(b'Nodes not ready yet, please retry later')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(sub_txt_content.encode('utf-8'))
            return

        if path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            homepage = (f'Hello world!<br><br>You can access /{SUB_PATH}'
                        f'(Default: /sub) get your nodes!').encode('utf-8')
            self.wfile.write(homepage)
            return

        self.send_response(404)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(b'Not Found')

    def log_message(self, format, *args):
        pass

# =========================== 主流程 ===========================
def start_server():
    global sub_txt_content, HY2_PORT

    # 1. 删除旧节点
    delete_nodes()

    # 2. 创建运行目录 + 清理文件
    create_directory()
    cleanup_old_files()

    # 3. 生成 Argo 隧道配置
    argo_type()

    # 4. 生成 Reality 密钥对 (仅当 REALITY_PORT 开启才生成)
    if is_valid_port(REALITY_PORT):
        generate_or_load_keypair()

    # 5. 生成 TLS 证书 (用于 Hysteria2)；失败则禁用 Hysteria2，保证其它协议正常运行
    if is_valid_port(HY2_PORT):
        try:
            ensure_tls_certificates(cert_path, key_path)
        except Exception as e:
            log_error(f'TLS certificate generation failed, disabling Hysteria2: {e}')
            HY2_PORT = ''

    # 6. 生成 Xray 配置
    generate_xray_config()

    # 7. 下载并运行文件
    download_files_and_run()

    # 8. 提取隧道域名并生成节点
    extract_domains()

    # 9. Telegram 推送 + 节点上传 + 自动保活
    send_telegram()
    upload_nodes()
    add_visit_task()

    # 10. 启动看门狗（节点已生成，此后子进程死了自动拉起）
    _start_watchdog()

    # 11. 90秒后清理文件
    clean_files()

# =========================== 信号处理 ===========================
def stop_all(signum=None, frame=None):
    """优雅关闭所有服务"""
    def shutdown():
        log('\nShutting down...')
        _shutdown_event.set()  # 先停看门狗，免得它在关停时又把进程拉起来
        for _name in ('xray', 'cloudflared', 'cfprobe'):
            try:
                _stop_child(_name)
            except Exception:
                pass
        # 兜底：清掉 _children 之外的孤儿进程
        pkill_match(web_name)
        pkill_match(bot_name)
        if CFP_ID and CFP_SECRET and CFP_URL:
            pkill_match(cf_probe_name)
        time.sleep(1)
        os._exit(0)

    t = threading.Thread(target=shutdown, daemon=True)
    t.start()

# =========================== 入口 ===========================
if __name__ == '__main__':
    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGTERM, stop_all)

    # 启动 HTTP 服务 (主线程)
    server = ThreadingHTTPServer(('0.0.0.0', PORT), RequestHandler)

    always_log(f'server is running on {PORT}!')

    # 在后台线程中启动主流程
    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    # 主线程阻塞在 HTTP 服务器上
    server.serve_forever()
