# -*- coding: utf-8 -*-
import ipaddress
from typing import Set

# 无效与回环 server 过滤黑名单
INVALID_SERVERS: Set[str] = {
    '0.0.0.0', '127.0.0.1', 'localhost', '::1', '[::1]', '::', '[::]', '1.1.1.1',
    'example.com', 'test.com', 'none', 'null', 'undefined'
}

# RFC 6598 运营商级 NAT (Carrier-Grade NAT) 网段
_CGNAT_NETWORK = ipaddress.ip_network('100.64.0.0/10')


def is_invalid_or_private_server(server: str) -> bool:
    """判断服务器地址是否属于无效域名、回环、私有内网、链路本地/云元数据或保留地址（防 SSRF）
    
    拦截范围包括：
    1. 空值、包含非法空白符（空格、换行、制表符）
    2. 明确的黑名单域名与占位符（localhost, example.com, none, null 等）
    3. 本机回环网段（127.0.0.0/8 包括 127.0.0.53 等，以及 IPv6 ::1）
    4. RFC 1918 私有局域网网段（10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16）
    5. 链路本地 / 云厂商元数据地址（169.254.0.0/16 包括 169.254.169.254，以及 IPv6 fe80::/10）
    6. 运营商级 CGNAT 网段（RFC 6598: 100.64.0.0/10）
    7. 多播、未指定与保留网段（0.0.0.0, 224.0.0.0/4, 240.0.0.0/4, IPv6 ::, fc00::/7 ULA）
    8. 正常合法公网 IP 与公网域名安全放行
    """
    if not server or any(c in server for c in (' ', '\n', '\r', '\t')):
        return True
    clean = server.lower().strip().strip('[]')
    if clean in INVALID_SERVERS or server.lower() in INVALID_SERVERS:
        return True
    try:
        ip = ipaddress.ip_address(clean)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
            or (ip.version == 4 and ip in _CGNAT_NETWORK)
        ):
            return True
    except ValueError:
        # 非 IP 地址，属于域名，安全放行由网络层后续解析
        pass
    return False
