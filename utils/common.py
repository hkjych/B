import base64
import binascii
import re

def b64encodes(s: str) -> str:
    """标准 Base64 编码"""
    if s is None:
        return ""
    return base64.b64encode(str(s).encode('utf-8')).decode('utf-8')

def b64decodes(s: str) -> str:
    """自动补齐 Padding 并支持标准与 URL-safe Base64 解码"""
    if not s:
        return ""
    # 清洗包括首尾及内部换行/空格的所有空白字符
    s = re.sub(r'\s+', '', str(s))
    # 核心修复：统一将 URL-Safe 字符转为标准 Base64 字符表 (- -> +, _ -> /)，彻底规避 b64decode 静默丢弃字符问题
    s_std = s.replace('-', '+').replace('_', '/')
    ss = s_std + '=' * ((4 - len(s_std) % 4) % 4)
    try:
        return base64.b64decode(ss.encode('utf-8')).decode('utf-8')
    except (UnicodeDecodeError, binascii.Error, ValueError):
        try:
            return base64.b64decode(ss.encode('utf-8')).decode('utf-8', errors='replace')
        except Exception:
            return ""
    except Exception:
        return ""

def b64decodes_safe(s: str) -> str:
    """URL-safe Base64 解码 (兼容器)"""
    return b64decodes(s)
