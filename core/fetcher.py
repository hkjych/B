import asyncio
import os
import re
import ipaddress
import socket
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Any, Optional, Tuple
import httpx
import yaml

from core.parser import Node
from utils.common import b64decodes
from utils.logger import logger

# 模块级预编译正则
GITHUB_RAW_PATTERN = re.compile(r'https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.*)')
URL_EXTRACT_PATTERN = re.compile(r'https?://[^\s)\]]+')
YAML_FALLBACK_PATTERN = re.compile(r'-\s*(\{.*?name:.*?\})', re.DOTALL)
from utils.constants import ALLOWED_PROTOCOLS

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://github.com/",
    "Sec-Ch-Ua": '"Not A(Brand";v="8", "Chromium";v="140", "Google Chrome";v="140"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1"
}

MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_RECURSIVE_URLS = 100
MAX_RECURSION_DEPTH = 1
MAX_REDIRECTS = 5

EXCLUDE_RECURSIVE_KEYWORDS = (
    'github.com/peasoft', 'license', 'readme', 'rules', 't.me/',
    'twitter.com', 'youtube.com', 'facebook.com', 't.cn', 'j.mp'
)

class Fetcher:
    def __init__(self, timeout: float = 10.0, connect_timeout: float = 5.0, max_concurrent: int = 15, client: Optional[httpx.AsyncClient] = None):
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.req_timeout = httpx.Timeout(timeout=timeout, connect=min(connect_timeout, timeout))
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.headers = DEFAULT_HEADERS
        self._external_client = client is not None
        self.client = client
        self._insecure_client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        if self.client is None:
            # 复用连接池、开启 Keep-Alive 与连接限制
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=30)
            self.client = httpx.AsyncClient(
                headers=self.headers,
                verify=True,
                follow_redirects=False,
                trust_env=False,
                limits=limits,
                timeout=self.req_timeout
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not self._external_client and self.client:
            await self.client.aclose()
            self.client = None
        if self._insecure_client:
            await self._insecure_client.aclose()
            self._insecure_client = None

    async def fetch_nodes(self, url: str, filters: Optional[Dict[str, Any]] = None, is_private: bool = False, verify_tls: bool = True, recursion_depth: int = 0) -> List[Node]:
        return await self._fetch_nodes_internal(url, filters, is_private=is_private, verify_tls=verify_tls, recursion_depth=recursion_depth)

    async def _validate_fetch_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"Rejected fetch URL: only credential-free HTTPS URLs are allowed ({url!r})")
        host = parsed.hostname.rstrip(".").lower()
        try:
            ip = ipaddress.ip_address(host)
            addresses = [ip]
        except ValueError:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
            addresses = [ipaddress.ip_address(info[4][0].split("%", 1)[0]) for info in infos]
        if not addresses or any(not address.is_global for address in addresses):
            raise ValueError(f"Rejected fetch URL resolving to non-public address: {host}")

    async def _request_limited(self, client: httpx.AsyncClient, url: str) -> bytes:
        current_url = url
        for redirect_count in range(MAX_REDIRECTS + 1):
            await self._validate_fetch_url(current_url)
            async with self.semaphore:
                async with client.stream("GET", current_url, timeout=self.req_timeout, follow_redirects=False) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location or redirect_count >= MAX_REDIRECTS:
                            raise ValueError("Redirect limit exceeded or missing Location header")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status_code != 200:
                        logger.debug(f"HTTP {response.status_code} on {current_url}")
                        return b""
                    declared_length = response.headers.get("content-length")
                    if declared_length and int(declared_length) > MAX_RESPONSE_BYTES:
                        raise ValueError(f"Response exceeded {MAX_RESPONSE_BYTES} byte limit")
                    chunks = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_RESPONSE_BYTES:
                            raise ValueError(f"Response exceeded {MAX_RESPONSE_BYTES} byte limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
        raise ValueError("Redirect limit exceeded")

    async def _fetch_nodes_internal(self, url: str, filters: Optional[Dict[str, Any]] = None, is_private: bool = False, verify_tls: bool = True, recursion_depth: int = 0) -> List[Node]:
        is_recursive = url.startswith('*')
        if is_recursive:
            url = url[1:]

        if recursion_depth > MAX_RECURSION_DEPTH:
            logger.warning(f"Recursive fetch depth limit reached for {url}")
            return []

        # 更加健壮的 GitHub 镜像生成逻辑
        targets = [url]
        gh_match = GITHUB_RAW_PATTERN.match(url)
        if gh_match:
            user, repo, branch, path = gh_match.groups()
            # 备选镜像 1: jsDelivr (极速稳定)
            targets.append(f"https://fastly.jsdelivr.net/gh/{user}/{repo}@{branch}/{path}")
            # 备选镜像 2: raw.gitmirror.com (直连加速镜像)
            targets.append(f"https://raw.gitmirror.com/{user}/{repo}/{branch}/{path}")
            # 备选镜像 3: ghfast.top (稳定通用代理)
            targets.append(f"https://ghfast.top/{url}")
            # 备选镜像 4: gh-proxy (兜底代理)
            targets.append(f"https://gh-proxy.com/{url}")

        content = None
        # 支持本地文件路径直读 (例如 file:///... 或相对/绝对路径)，方便离线私密机场与本地测试
        clean_file_path = url.replace('file:///', '').replace('file://', '')
        if os.path.isfile(clean_file_path):
            try:
                with open(clean_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f"Failed to read local file {clean_file_path}: {e}")

        # 若非本地文件，则执行网络镜像请求
        if not content:
            client = self.client if verify_tls else self._insecure_client
            close_client_after = False
            if client is None:
                client = httpx.AsyncClient(headers=self.headers, verify=verify_tls, follow_redirects=False, trust_env=False, timeout=self.req_timeout)
                if verify_tls and self.client is None:
                    self.client = client
                elif not verify_tls:
                    self._insecure_client = client
                else:
                    close_client_after = True

            request_errors = []
            try:
                for target_url in targets:
                    try:
                        logger.debug(f"Fetching: {target_url}")
                        if not verify_tls and self._external_client:
                            raise ValueError("verify_tls=false is unsupported with an externally supplied client")
                        payload = await self._request_limited(client, target_url)
                        if payload:
                            text = payload.decode('utf-8-sig', errors='ignore')
                            # 识别假 200（如反代 404/502 HTML、Cloudflare 质询页）
                            head_sample = text[:500].upper()
                            if '<!DOCTYPE' in head_sample or '<HTML' in head_sample:
                                logger.debug(f"  - Target {target_url} returned HTML webpage instead of raw data, trying next mirror.")
                                continue
                            content = text
                            break
                        else:
                            logger.debug(f"  - Empty response for {target_url}")
                    except Exception as e:
                        request_errors.append(f"{target_url}: {type(e).__name__}: {e}")
                        logger.debug(f"  - Request Exception on {target_url}: {e}")
            finally:
                if close_client_after:
                    await client.aclose()

        if not content:
            logger.warning(f"  - Failed to get any content for {url}")
            detail = "; ".join(request_errors[-3:]) if 'request_errors' in locals() and request_errors else "no successful response"
            raise RuntimeError(f"No content retrieved from source: {url} ({detail})")

        if is_recursive:
            found_urls = URL_EXTRACT_PATTERN.findall(content)
            sub_urls = []
            for u in found_urls:
                u_lower = u.lower()
                if any(x in u_lower for x in EXCLUDE_RECURSIVE_KEYWORDS):
                    continue
                sub_urls.append(u)

            if sub_urls:
                sub_urls = list(dict.fromkeys(sub_urls))[:MAX_RECURSIVE_URLS]
                logger.info(f"  - Fetching up to {len(sub_urls)} sub-urls in {url}")
                tasks = [self.fetch_nodes(u, filters, is_private=is_private, verify_tls=verify_tls, recursion_depth=recursion_depth + 1) for u in sub_urls]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                all_nodes = []
                failures = 0
                for res in results:
                    if isinstance(res, list):
                        all_nodes.extend(res)
                    else:
                        failures += 1
                        logger.warning(f"Recursive child fetch failed: {type(res).__name__}: {res}")
                if failures == len(results):
                    raise RuntimeError(f"All recursive child fetches failed for {url}")
                return all_nodes

        # 解析内容
        nodes = self.parse_content(content)

        # 协议过滤
        if filters and 'ignore' in filters:
            raw_ignore = filters['ignore']
            if isinstance(raw_ignore, list):
                raw_types = raw_ignore
            else:
                raw_types = str(raw_ignore).split(',')
            
            ignore_types = set()
            for t in raw_types:
                t_clean = str(t).strip().lower()
                ignore_types.add(t_clean)
                if t_clean == 'hy2':
                    ignore_types.add('hysteria2')
                elif t_clean == 'hysteria2':
                    ignore_types.add('hy2')

            nodes = [n for n in nodes if str(getattr(n, 'type', '')).lower() not in ignore_types]

        if is_private:
            for n in nodes:
                n.data['_is_private'] = True

        if nodes:
            logger.info(f"  - Successfully parsed {len(nodes)} nodes from {url}")
        else:
            logger.warning(f"  - No nodes found in {url}")

        return nodes

    def parse_content(self, content: str) -> List[Node]:
        nodes = []

        # 0. 预检查：如果是 HTML 网页，直接跳过（防止报错，使用前 1000 字符切片避免全量大文本内存复制）
        head_sample = content[:1000].upper()
        if '<!DOCTYPE' in head_sample or '<HTML' in head_sample:
            logger.debug("  - Warning: Content looks like HTML/Webpage, skipping parser.")
            return []

        # 1. Try to parse as YAML (Clash style)
        # 性能优化：快速预检关键词，纯 URL 链接文本与 Base64 文本直接跳过 YAML 解析
        is_potential_yaml = (
            "proxies:" in content or 
            "Proxy:" in content or 
            "payload:" in content or 
            ("server:" in content and "port:" in content)
        )
        if is_potential_yaml:
            try:
                data = yaml.safe_load(content)
                if isinstance(data, dict):
                    plist = data.get("proxies") or data.get("Proxy")
                    if isinstance(plist, list):
                        for p in plist:
                            if isinstance(p, dict):
                                nodes.append(Node(p))
                elif isinstance(data, list):
                    for p in data:
                        if isinstance(p, dict):
                            nodes.append(Node(p))
            except Exception as e:
                logger.debug(f"YAML parsing failed: {type(e).__name__}: {e}")

            # 2. 如果 YAML 整体解析失败，尝试正则表达式提取保底
            if not nodes:
                found_lines = YAML_FALLBACK_PATTERN.findall(content)
                for line in found_lines:
                    try:
                        clean_line = line.replace('\n', ' ').replace('\r', '')
                        p_data = yaml.safe_load(clean_line)
                        if isinstance(p_data, dict) and 'server' in p_data:
                            nodes.append(Node(p_data))
                    except Exception as e:
                        logger.debug(f"YAML fallback row skipped: {type(e).__name__}: {e}")
                        continue

            if nodes:
                return nodes

        # 3. Try to parse as Base64 (Standard V2Ray style)
        if len(content) > 10 and not any(s in content for s in ["server:", "port:", "type:"]):
            first_line = content.strip().splitlines()[0].strip().lower() if content.strip() else ""
            if not first_line.startswith(ALLOWED_PROTOCOLS):
                try:
                    decoded = b64decodes(content)
                    if decoded:
                        lines = decoded.splitlines()
                        for line in lines:
                            line_s = line.strip()
                            if line_s.lower().startswith(ALLOWED_PROTOCOLS):
                                nodes.append(Node(line_s))
                except Exception as e:
                    logger.debug(f"Base64 subscription parsing failed: {type(e).__name__}: {e}")

        if nodes:
            return nodes

        # 4. Try to parse as raw list (one URL per line)
        for line in content.splitlines():
            line_s = line.strip()
            if line_s.lower().startswith(ALLOWED_PROTOCOLS):
                nodes.append(Node(line_s))

        return nodes

async def parallel_fetch(source_infos: List[Dict[str, Any]], timeout: float = 10.0, connect_timeout: float = 5.0) -> Tuple[List[Node], List[Dict[str, Any]]]:
    """
    接收格式化的 source_info 列表，包含 name, url 和 filters
    使用全局连接池高效并行抓取，返回 (全量节点列表, 按源归类的明细列表)
    """
    async with Fetcher(timeout=timeout, connect_timeout=connect_timeout) as fetcher:
        tasks = [fetcher.fetch_nodes(info['url'], info.get('filters'), is_private=info.get('is_private', False), verify_tls=info.get('verify_tls', True)) for info in source_infos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_nodes = []
        source_results = []
        for info, res in zip(source_infos, results):
            s_name = info.get('name', '未命名源')
            is_priv = info.get('is_private', False)
            if isinstance(res, Exception) or not res:
                source_results.append({
                    'name': s_name,
                    'nodes': [],
                    'is_private': is_priv,
                    'ok': False,
                    'error': f'{type(res).__name__}: {res}' if isinstance(res, Exception) else 'No proxy nodes parsed'
                })
            else:
                for n in res:
                    if '_source' not in n.data:
                        n.data['_source'] = s_name
                all_nodes.extend(res)
                source_results.append({
                    'name': s_name,
                    'nodes': res,
                    'is_private': is_priv,
                    'ok': True,
                    'error': None
                })
        return all_nodes, source_results
