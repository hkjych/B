import asyncio
import datetime
import os
import time
import yaml

from core.fetcher import parallel_fetch
from core.processor import NodeProcessor
from core.generator import Generator
from utils.stats import update_readme_all, prepare_source_stats
from utils.notify import send_tg_notification
from utils.logger import logger

from typing import Any, Dict, List

TEMPLATE_FILE = "config.yaml"
OUTPUT_FILE = "list.meta.yml"

def _normalize_private_sources(data: Any) -> List[Dict[str, Any]]:
    """规范化私有源数据结构并自动注入 is_private=True 标记"""
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get('sources') or []
    else:
        items = []

    valid_items = []
    for item in items:
        if isinstance(item, dict):
            item['is_private'] = True
            valid_items.append(item)
    return valid_items

async def main():
    # 1. Load Sources from YAML
    sources_file = "sources.yaml"
    if not os.path.exists(sources_file):
        logger.error(f"{sources_file} not found.")
        return

    now = datetime.datetime.now()
    source_infos = []
    smart_pool_settings = {}
    try:
        with open(sources_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            sources_data = data.get('sources') or []
            smart_pool_settings = (data.get('settings') or {}).get('smart_pool', {}) or {}
    except Exception as e:
        logger.error(f"Failed to read {sources_file}: {e}")
        return
        
    # 标记公共源（若 sources.yaml 中明确配置 is_private: true 则尊重配置）
    for s in sources_data:
        if isinstance(s, dict):
            s['is_private'] = bool(s.get('is_private', False))

    # 1. 尝试从本地 private_sources.yaml 加载私有源 (用于本地测试与安全防泄漏)
    local_priv_file = os.path.join(os.path.dirname(__file__), 'private_sources.yaml')
    if os.path.exists(local_priv_file):
        try:
            with open(local_priv_file, 'r', encoding='utf-8') as f:
                lp_sources = _normalize_private_sources(yaml.safe_load(f))
                sources_data.extend(lp_sources)
                logger.info(f"Loaded {len(lp_sources)} private sources from local private_sources.yaml.")
        except Exception as e:
            logger.warning(f"Failed to load local private_sources.yaml: {e}")

    # 2. Append private sources from Environment Variable (GitHub Secrets)
    private_sources = os.getenv('PRIVATE_SOURCES')
    if private_sources:
        try:
            sec_sources = _normalize_private_sources(yaml.safe_load(private_sources))
            sources_data.extend(sec_sources)
            logger.info(f"Loaded {len(sec_sources)} private sources from Secrets.")
        except Exception as e:
            logger.warning(f"Failed to parse PRIVATE_SOURCES: {e}")
            
    for s in sources_data:
        if isinstance(s, dict):
            if s.get('enabled') is False:
                continue
            url = s.get('url')
            if not url or not isinstance(url, str):
                continue
            name = s.get('name', '未命名源')
            
            # Handle date placeholders in URL
            url = url.replace('%Y', now.strftime('%Y'))
            url = url.replace('%m', now.strftime('%m'))
            url = url.replace('%d', now.strftime('%d'))
            
            # Translate recursive flag to * prefix
            if s.get('recursive') and not url.startswith('*'):
                url = '*' + url
            
            ignore = s.get('ignore')
            filters = {'ignore': ignore} if ignore else {}
            
            source_infos.append({
                'name': name,
                'url': url,
                'filters': filters,
                'is_private': bool(s.get('is_private', False))
            })
    
    if not source_infos:
        logger.warning("No active sources found.")
        return

    start_time = time.time()
    
    # 获取来源数量用于统计
    active_source_count = len(source_infos)
    logger.info(f"Starting fetching from {active_source_count} active sources...")
    
    # 2. Parallel fetching (单次全异步并发抓取，同时获取各源节点明细)
    all_raw_nodes, raw_source_results = await parallel_fetch(source_infos)
    raw_count = len(all_raw_nodes)
    logger.info(f"Fetched {raw_count} raw nodes.")
    
    # 3. Processing (Deduplicate, Clean Names, Emoji Flags)
    processor = NodeProcessor()
    processed_nodes = processor.process_all(all_raw_nodes)
    
    # 4. Generate Output (Merge with template)
    if not os.path.exists(TEMPLATE_FILE):
        logger.warning(f"{TEMPLATE_FILE} not found. Using node list only.")
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            yaml.dump({"proxies": [n.to_clash() for n in processed_nodes]}, f, allow_unicode=True)
    else:
        elapsed_time = time.time() - start_time
        generator = Generator(TEMPLATE_FILE, pool_settings=smart_pool_settings)
        gen_stats = generator.generate(processed_nodes, OUTPUT_FILE, active_source_count, raw_count, elapsed_time)
        
        # 5. Update README (统一更新顶部徽章、地区统计表与各源贡献度明细)
        try:
            source_stats = prepare_source_stats(raw_source_results, final_nodes=processed_nodes)
            update_readme_all(gen_stats, source_stats, now=now)
        except Exception as e:
            logger.warning(f"Failed to update README stats table: {e}")

        # 6. Telegram Notification (直接内存传参，静默容错保护)
        if gen_stats:
            try:
                send_tg_notification(gen_stats)
            except Exception as e:
                logger.warning(f"Failed to send Telegram notification: {e}")
    
    logger.info(f"All done! Generated: {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())
