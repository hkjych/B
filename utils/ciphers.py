from typing import Optional

# Shadowsocks 常见非标准别名 -> Clash / Mihomo 官方标准名称映射表
SS_CIPHER_ALIASES: dict[str, str] = {
    # ChaCha20-Poly1305 变体（常见漏写 ietf）
    'chacha20-poly1305': 'chacha20-ietf-poly1305',
    'chacha20-ietf-poly-1305': 'chacha20-ietf-poly1305',
    'xchacha20-poly1305': 'xchacha20-ietf-poly1305',
    'xchacha20-ietf-poly-1305': 'xchacha20-ietf-poly1305',

    # AES-GCM 常见缺少连字符或别名
    'aes128-gcm': 'aes-128-gcm',
    'aes192-gcm': 'aes-192-gcm',
    'aes256-gcm': 'aes-256-gcm',

    # 常见流加密别名
    'rc4md5': 'rc4-md5',
    'rc4_md5': 'rc4-md5',
}

# Clash / Mihomo 内核支持的合法 Shadowsocks 加密算法集合
VALID_SS_CIPHERS: set[str] = {
    # AEAD Ciphers
    'aes-128-gcm',
    'aes-192-gcm',
    'aes-256-gcm',
    'chacha20-ietf-poly1305',
    'xchacha20-ietf-poly1305',

    # Shadowsocks 2022
    '2022-blake3-aes-128-gcm',
    '2022-blake3-aes-256-gcm',
    '2022-blake3-chacha20-poly1305',

    # Stream Ciphers (Legacy)
    'aes-128-cfb',
    'aes-192-cfb',
    'aes-256-cfb',
    'aes-128-ctr',
    'aes-192-ctr',
    'aes-256-ctr',
    'rc4-md5',
    'chacha20-ietf',
    'chacha20',
    'xchacha20',
}


def normalize_ss_cipher(cipher: Optional[str]) -> str:
    """
    归一化 Shadowsocks 加密算法名称。
    去除首尾空格、转换为小写，并将常见非标准别名（如 chacha20-poly1305）映射为标准名称。
    """
    if not cipher:
        return ''
    c = str(cipher).strip().lower()
    return SS_CIPHER_ALIASES.get(c, c)


def is_valid_ss_cipher(cipher: Optional[str]) -> bool:
    """
    校验加密算法是否为 Clash / Mihomo 支持的合法 Shadowsocks 加密方式。
    """
    if not cipher:
        return False
    norm = normalize_ss_cipher(cipher)
    return norm in VALID_SS_CIPHERS
