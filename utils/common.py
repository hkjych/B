import base64
import binascii
import re
from typing import Any

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


# 严格模式控制字符过滤正则：清理所有 C0/C1 控制字符、零宽字符、格式字符 (含 \t, \n, \r)
STRICT_CONTROL_REGEX = re.compile(
    r'[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff\ufffe\uffff]'
)

# 宽松/YAML 兼容模式控制字符过滤正则：保留 YAML 结构必需的 \t (\x09), \n (\x0a), \r (\x0d)
YAML_SAFE_CONTROL_REGEX = re.compile(
    r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff\ufffe\uffff]'
)


def deep_sanitize(data: Any, preserve_newlines: bool = False) -> Any:
    """递归清理字典、列表或字符串中的非法控制字符与不可见字符。
    
    :param data: 待清洗的数据结构 (str, dict, list 或其它)
    :param preserve_newlines: 若为 True，则保留 YAML 结构必需的 \\t, \\n, \\r
    """
    regex = YAML_SAFE_CONTROL_REGEX if preserve_newlines else STRICT_CONTROL_REGEX
    if isinstance(data, str):
        return regex.sub('', data)
    elif isinstance(data, dict):
        return {
            (regex.sub('', k) if isinstance(k, str) else k): deep_sanitize(v, preserve_newlines=preserve_newlines)
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [deep_sanitize(item, preserve_newlines=preserve_newlines) for item in data]
    return data

