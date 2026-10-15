# 📋 MetaFetch 代码优化修改计划

> 基于 2026-10-15 全量代码审计报告整理 | 共 4 阶段 27 项改动

---

## 阶段一：🔴 P0 紧急修复（阻断性 / 高危）

### 1.1 地区匹配算法重构
- **问题**：子串无边界匹配导致 `Austria→AU`、`Indonesia→IN`、`Cyprus→RU`；2 字母代码大小写忽略导致 `No→挪威`、`ID→印尼`
- **涉及文件**：`utils/regions.py`
- **修改方案**：
  1. `_LONG_KEYWORDS` 按关键词长度**降序排列**，优先匹配完整国名
  2. 2 字母国家代码改为**大写严格匹配**（去掉 `re.IGNORECASE`）
  3. 3 字母缩写增加词边界检查，防止 `AUS` 匹配到 `AUStria`
  4. 移除 `keywords` 中的 Emoji 旗帜（如 `🇨🇵`），改用 Emoji 表映射
- **验证**：新增 `tests/test_regions.py`，覆盖所有已知碰撞用例

### 1.2 私有源名称防泄漏
- **问题**：`source_stats` 未过滤 `is_private`，私有机场名称直接渲染到公开 README
- **涉及文件**：`main.py` L137-144
- **修改方案**：
  ```python
  for item in raw_source_results:
      if item.get('is_private'):
          continue  # 跳过私有源
      valid_nodes = processor.filter_invalid(item.get('nodes', []))
      source_stats.append({...})
  ```

### 1.3 修复 `plugin-opts: None` 崩溃
- **问题**：`dict.get(key, default)` 在 key 存在但值为 `None` 时返回 `None` 而非 default
- **涉及文件**：`core/processor.py` L168-170, L188-190
- **修改方案**：
  ```python
  # 所有 plugin-opts 取值统一改为：
  opts = n_data.get('plugin-opts') or {}
  ```

### 1.4 `deep_sanitize` 执行顺序前置
- **问题**：零宽字符在去重阶段未被清除，导致重复节点通过
- **涉及文件**：`core/processor.py` L223-228
- **修改方案**：
  ```python
  def process_all(self, nodes):
      # Step 0: 先清洗不可见字符
      for node in nodes:
          node.data = deep_sanitize(node.data)
      nodes = self.filter_invalid(nodes)   # Step 1
      nodes = self.deduplicate(nodes)       # Step 2
      self.clean_and_rename(nodes)          # Step 3
      return nodes
  ```
  同时在 `clean_and_rename` 中移除重复的 `deep_sanitize` 调用

### 1.5 Base64 解码修复
- **问题**：URL-Safe Base64 中的 `-` 被 `b64decode` 静默丢弃导致数据损坏
- **涉及文件**：`utils/common.py` L18-24
- **修改方案**：
  ```python
  def b64decodes(s: str) -> str:
      if not s: return ""
      s = re.sub(r'\s+', '', str(s))
      s_std = s.replace('-', '+').replace('_', '/')  # 统一转标准字符表
      ss = s_std + '=' * ((4 - len(s_std) % 4) % 4)
      try:
          return base64.b64decode(ss.encode('utf-8')).decode('utf-8')
      except Exception:
          return ""
  ```
  同时考虑移除冗余的 `b64decodes_safe`

### 1.6 递归抓取信号量下沉
- **问题**：父任务持有信号量等待子任务，子任务又争抢同一信号量 → 死锁
- **涉及文件**：`core/fetcher.py` L65-67, L144-145
- **修改方案**：
  1. `fetch_nodes` 去掉 `async with self.semaphore` 包裹
  2. 信号量下沉到底层 `_do_http_get`（实际发起 HTTP 请求的方法）
  3. 或改为递归子任务直接调用 `_fetch_nodes_internal`（绕过信号量）

---

## 阶段二：🟠 P1 功能性 Bug 修复

### 2.1 SS 节点 URL 尾部斜杠处理
- **涉及文件**：`core/parser.py` L150-156
- **修改**：解析 `serverinfo` 前 `serverinfo = serverinfo.rstrip('/')`

### 2.2 VMess TLS 字段兼容
- **涉及文件**：`core/parser.py` L109
- **修改**：
  ```python
  'tls': str(v.get('tls', '')).strip().lower() in ('tls', 'true', '1') or v.get('tls') is True,
  ```

### 2.3 `get_identity()` 补充 plugin/obfs 信息
- **涉及文件**：`core/parser.py` L414-456
- **修改**：在 `ident_parts` 末尾追加：
  ```python
  if self.data.get('plugin'):
      ident_parts.append(f"plugin:{self.data['plugin']}")
  if self.data.get('obfs'):
      ident_parts.append(f"obfs:{self.data['obfs']}")
  ```

### 2.4 精选池容量逻辑修正
- **涉及文件**：`core/generator.py` L356-380
- **修改**：将 `max_pool_size` 截断移至所有补齐/兜底逻辑**之后**作为最终步骤：
  ```python
  # 所有填充和兜底完成后，再做最终截断
  if max_pool_size != float('inf') and len(smart_pool_nodes) > int(max_pool_size):
      smart_pool_nodes = smart_pool_nodes[:int(max_pool_size)]
  ```

### 2.5 私有中国节点过滤修正
- **涉及文件**：`core/generator.py` L255
- **修改**：`name.startswith('🇨🇳')` → `'🇨🇳' in name`

### 2.6 Base64 解码后增加协议过滤
- **涉及文件**：`core/fetcher.py` L229-234
- **修改**：
  ```python
  for line in lines:
      line_s = line.strip()
      if line_s and line_s.lower().startswith(ALLOWED_PROTOCOLS):
          nodes.append(Node(line_s))
  ```

### 2.7 `main.py` 空配置防御
- **涉及文件**：`main.py` L31, L46-51
- **修改**：
  ```python
  smart_pool_settings = (data.get('settings') or {}).get('smart_pool', {}) or {}
  lp_sources = lp_data if isinstance(lp_data, list) else (lp_data.get('sources') or [])
  ```

### 2.8 Telegram 通知 HTML 转义
- **涉及文件**：`utils/notify.py` L33-46
- **修改**：引入 `import html`，所有插值变量包裹 `html.escape(...)`

---

## 阶段三：🟡 P2 健壮性加固

### 3.1 IPv6 回环地址过滤补全
- **涉及文件**：`core/processor.py` L46-49
- **修改**：检查前 `n_server = n_server.strip('[]')`，并在 `INVALID_SERVERS` 中补充 `'[::1]'`

### 3.2 SNI 字段统一
- **涉及文件**：`core/parser.py` 多处 `_load_*` 和 `to_url()`
- **修改**：所有协议统一使用 `sni` 字段名；`to_url()` 统一检查 `self.data.get('sni') or self.data.get('servername')`

### 3.3 测速 0 速节点降分
- **涉及文件**：`core/generator.py` L159-166
- **修改**：
  ```python
  speed = float(m_mb.group(1))
  score = (100.0 + speed) if speed > 0 else 5.0  # 0速节点极低分
  ```

### 3.4 `_yaml_v3_needs_quotes` 移除裸十六进制误判
- **涉及文件**：`core/generator.py` L58-62
- **修改**：删除 `int(plain, 16)` 分支，仅保留 `int(plain, 0)` 处理带 `0x` 前缀的十六进制

### 3.5 Shields.io 徽章日期转义
- **涉及文件**：`utils/stats.py` L19-21
- **修改**：`.replace('-', '--').replace(' ', '--').replace(':', '%3A')`

### 3.6 源名称 Markdown 转义
- **涉及文件**：`utils/stats.py` L80-81
- **修改**：`safe_name = str(name).replace('|', '-').replace('`', "'")`

### 3.7 私有 IP 网段过滤（防 SSRF）
- **涉及文件**：`core/processor.py` L46-49
- **修改**：引入 `ipaddress` 模块，补充 RFC 1918 私有网段 + 云元数据地址过滤

### 3.8 协议白名单统一定义
- **涉及文件**：新增 `utils/constants.py`
- **修改**：将 `ALLOWED_PROTOCOLS`、`ALLOWED_TYPES` 提取到统一常量模块，各文件引用

### 3.9 YAML 输出改为 `allow_unicode=True`
- **涉及文件**：`core/generator.py` L411
- **修改**：`yaml.dump(..., allow_unicode=True)`，中文和 Emoji 直接可读

---

## 阶段四：🟢 P3 代码质量与性能优化

### 4.1 消除代码重复
| 重复项 | 修改方案 |
|---|---|
| `deep_sanitize` 两份 | 统一提取到 `utils/common.py`，提供严格/宽松两个模式参数 |
| `parser.py` 类型归一化重复 | 移除 L11-15，保留 L24-29 |
| VMess cipher 校验重复 | 集中在 `_clean_dict_fields` |
| Reality 解析重复 | 提取 `_parse_reality_opts()` 辅助方法 |
| `is_private` 标记重复 3 次 | 提取 `_normalize_private_sources(sources)` |
| `node_obj_map` 重复构建 | 复用 `name_to_node`，删除 L226 |

### 4.2 性能优化
| 优化项 | 修改方案 |
|---|---|
| `get_identity()` 每次重算 | 添加 `_identity_cache` 属性缓存 |
| `re.sub` 循环内编译 | 提升为模块级 `STRIP_PUNCT_REGEX` |
| 未匹配地区二次扫描 | 始终设置 `node.data['_region']`（含 `None`） |
| `content.upper()` 全文复制 | 改为 `content[:1000].upper()` 切片 |
| 纯链接文本走 `yaml.safe_load` | 预检 `proxies:` 关键字再决定 |
| `active_keys.sort()` 多余排序 | 删除，Python 3.7+ dict 已保序 |

### 4.3 补充单元测试
| 新增测试文件 | 覆盖内容 |
|---|---|
| `tests/test_regions.py` | 子串碰撞、2 字母歧义、Emoji 匹配 |
| `tests/test_main.py` | YAML 加载、环境变量私有源、空配置防御 |
| `tests/test_notify.py` | HTML 转义、消息格式、异常处理 |
| 补充 `test_common.py` | URL-Safe Base64、None 输入 |
| 补充 `test_fetcher.py` | `parallel_fetch`、递归抓取、镜像降级 |
| 补充 `test_generator.py` | `is_china_node` 前缀豁免、0 速评分、空节点 |
| 补充 `test_processor.py` | `plugin-opts: None`、IPv6 回环、端口边界 |

### 4.4 配置与 CI 优化
| 改动项 | 修改方案 |
|---|---|
| `config.yaml` 测速组 | `lazy: true` 或 `interval: 300`，防移动端耗电 |
| `config.yaml` 安全 | `external-controller` 补充 `secret` 占位注释 |
| `config.yaml` 规则 | 补充 `DOMAIN-SUFFIX,x.com,🚀 选择代理` |
| `fetch.yml` 触发优化 | 添加 `paths-ignore: ['README.md', 'list.*']` |
| `notify.py` 死代码 | 移除 `tg_summary.txt` 读取分支 |
| `processor.py` `GROUP_NAMES` | 补充 `👑 私有节点`、`⚡ 自动选择 \| 👑 私有节点` |
| `processor.py` API 一致性 | `clean_and_rename` 增加 `return nodes` |

---

## 执行建议

> [!IMPORTANT]
> **建议按阶段逐步实施**，每个阶段完成后运行全量测试确认无回归：
> 1. **阶段一（P0）**：立即修复，防止数据泄漏和程序崩溃
> 2. **阶段二（P1）**：紧随其后，修复节点丢失和逻辑错误
> 3. **阶段三（P2）**：加固防御，提升健壮性
> 4. **阶段四（P3）**：代码清理和性能优化，最后补齐测试
