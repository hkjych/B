# -*- coding: utf-8 -*-
"""
全局通用常量定义模块
"""

# 支持的代理协议 Scheme 前缀元组 (用于 URL 快速匹配与白名单前缀检查)
ALLOWED_PROTOCOLS = (
    'vmess://',
    'vless://',
    'ss://',
    'trojan://',
    'hy2://',
    'hysteria2://',
)

# 支持的代理节点协议类型名称集合 (包含别名，如 hy2，用于 Node.type 校验)
ALLOWED_TYPES = {
    'vmess',
    'vless',
    'ss',
    'trojan',
    'hysteria2',
    'hy2',
}

# 核心规范化协议名称集合 (不含别名，如 hy2 统一归一化为 hysteria2)
CANONICAL_PROTOCOLS = {
    'vmess',
    'vless',
    'ss',
    'trojan',
    'hysteria2',
}
