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

### 1.6 递归抓取信号量下沉 [✅ 已完成]
- **问题**：父任务持有信号量等待子任务，子任务又争抢同一信号量 → 死锁
- **涉及文件**：`core/fetcher.py` L65-67, L108-110, `tests/test_fetcher.py`
- **完成情况**：`fetch_nodes` 移除外层 `self.semaphore`，下沉至底层 `client.get` 网络请求，新增 `test_recursive_fetch_semaphore_no_deadlock` 单元测试验证零死锁。

---

## 阶段二：🟠 P1 功能性 Bug 修复

### 2.1 SS 节点 URL 尾部斜杠处理 [✅ 已完成]
- **涉及文件**：`core/parser.py` L148-156, `tests/test_parser.py`
- **完成情况**：解析 `serverinfo` 前增加 `.strip().split('/')[0].strip()` 剥离斜杠和路径，增强 IPv6/插件及全量 Base64 尾部斜杠容错；新增 `test_node_from_ss_url_with_trailing_slash` 4 组单元测试全部通过。

### 2.2 VMess TLS 字段兼容 [✅ 已完成]
- **涉及文件**：`core/parser.py` L100-112, `tests/test_parser.py`
- **完成情况**：支持布尔值 `True`、数字 `1` 以及大小写字符串 `tls`/`TLS`/`true`；同时对 `net` 字段（`ws`/`grpc`）增加 `.lower()` 规范化处理；新增 `test_node_from_vmess_tls_compatibility` 覆盖 14 种 TLS 开启与关闭测试用例全部通过。

### 2.3 `get_identity()` 补充 plugin/obfs 信息 [✅ 已完成]
- **涉及文件**：`core/parser.py` L464-483, `tests/test_parser.py`
- **完成情况**：在 `ident_parts` 中细致引入 `plugin`（包含 `pmod` 模式与 `phost` 伪装域名）以及 `obfs`（包含混淆密码 `opwd`）特征维度，彻底避免带混淆/插件与普通节点被误判去重；新增 `test_get_identity_with_plugin_and_obfs` 单元测试全部通过。

### 2.4 精选池容量逻辑修正 [✅ 已完成]
- **涉及文件**：`core/generator.py` L350-390, `tests/test_generator.py`
- **完成情况**：将全局最大容量 `max_pool_size` 的截断逻辑下沉移至 `min_pool_size` 补齐与极端兜底之后作为最终把关道闸，并优先保全私有节点，杜绝任何兜底分支将海量节点灌入自动测速组引发测速风暴；新增 `test_generator_max_pool_size_strict_cap_after_fallback` 单元测试全部通过。

### 2.5 私有中国节点过滤修正 [✅ 已完成]
- **涉及文件**：`core/generator.py` L255, `tests/test_generator.py`
- **完成情况**：将 `is_china_node(name)` 中针对国旗的判断修正为 `'🇨🇳' in name`，确保被冠以 `👑 ` 标识的私有中国境内节点能够被精准识别并坚决排除出 `♻️ 自动选择` / `🔰 延迟最低` 精选测速池（同时完整保留于专属的 `👑 私有节点` 组内）；新增 `test_generator_private_china_node_excluded_from_smart_pool` 单元测试全部通过。

### 2.6 Base64 解码后增加协议过滤 [✅ 已完成]
- **涉及文件**：`core/fetcher.py` L229-237, `tests/test_fetcher.py`
- **完成情况**：在 Base64 解码后的逐行处理中严格执行 `ALLOWED_PROTOCOLS` 白名单前缀过滤，有效拦截订阅列表中掺杂的 Telegram 广告、公告说明与 HTTP 非代理杂质文本，杜绝畸形 Node 对象实例化及潜在解析异常；新增 `test_parse_content_base64_protocol_filter_ignores_ads_and_text` 单元测试全部通过。

### 2.7 `main.py` 空配置防御 [✅ 已完成]
- **涉及文件**：`main.py` L31, L46-51, `tests/test_main.py`
- **完成情况**：在 `main.py` 中引入 `(data.get('settings') or {})...` 链式短路安全取值与 `isinstance(lp_data, list)` 格式自适应兼容，彻底解决 YAML 配置留空（`None`）或列表格式引发的 `AttributeError` 崩溃；新增 `test_sources_yaml_empty_settings_defense` 与 `test_private_sources_formats_defense` 单元测试全部通过。

### 2.8 Telegram 通知 HTML 转义 [✅ 已完成]
- **涉及文件**：`utils/notify.py` L1, L17, L25, `tests/test_notify.py`
- **完成情况**：在 `utils/notify.py` 中引入 `import html`，对格式化模板中插入的时间戳、动态地区名称等插值变量严谨包裹 `html.escape(...)`，彻底杜绝特殊字符破坏 Telegram HTML 解析导致的 `HTTP 400 Bad Request` 发送失败异常；新增 `test_format_tg_summary_normal` 与 `test_format_tg_summary_html_escaping` 单元测试全部通过。

---

## 阶段三：🟡 P2 健壮性加固

### 3.1 IPv6 回环地址过滤补全 [✅ 已完成]
- **涉及文件**：`core/processor.py` L47-50, L138, `tests/test_processor.py`
- **完成情况**：在 `INVALID_SERVERS` 黑名单中补齐了 `'[::1]'`, `'::'`, `'[::]'`，并在 `filter_invalid()` 中对服务器地址执行 `strip('[]')` 预处理，彻底过滤各种带括号/裸写的 IPv6 回环及未指定地址假节点，同时确保合法外网 IPv6 节点不受影响；在 `test_processor_filter_invalid_servers` 补充针对性单测全部通过。

### 3.2 SNI 字段统一 [✅ 已完成]
- **涉及文件**：`core/parser.py` L88-93, L123, L235, L268-270, L303, L374, L400, L417, `tests/test_parser.py`
- **完成情况**：在所有协议（VMess、VLESS、Trojan、Hysteria2）的 URL 解析和字典清洗时统一以 `sni` 为标准字段，并双向兼容 `servername`；在 `to_url()` 导出时统一通过 `self.data.get('sni') or self.data.get('servername')` 提取，确保无论源格式为何种命名均可完整导出 `sni=` 参数，消弭跨内核协议导出差异与去重指纹漂移；新增 `test_sni_and_servername_unification` 单元测试全部通过。

### 3.3 测速 0 速节点降分 [✅ 已完成]
- **涉及文件**：`core/generator.py` L159-174, `tests/test_generator.py`
- **完成情况**：在 `get_node_quality_score()` 中对测速结果进行有效性校验（`speed > 0`）；若测速值为 0.0 MB/s 或 0 KB/s（表明节点已超时断连挂掉），果断降权至 5.0 分垫底，彻底杜绝死节点拿 100 分高分并被排在精选池前面的问题；新增 `test_generator_zero_speed_nodes_demotion` 单元测试全部通过。

### 3.4 `_yaml_v3_needs_quotes` 移除裸十六进制误判 [✅ 已完成]
- **涉及文件**：`core/generator.py` L58-62, `tests/test_generator.py`
- **完成情况**：移除 `_yaml_v3_needs_quotes` 中的 `int(plain, 16)` 误判分支，仅保留 `int(plain, 0)` 检测合法的前缀进制数（`0x`、`0o`、`0b`）；彻底杜绝了无前缀的裸十六进制字符串（如密码、MD5 哈希值、混淆密码等）被误加双引号的问题，保持 YAML 导出的简洁规范；新增 `test_yaml_v3_needs_quotes` 及针对 SafeDumper 导出的单元测试全部通过。

### 3.5 Shields.io 徽章日期转义 [✅ 已完成]
- **涉及文件**：`utils/stats.py` L18-22, `tests/test_stats.py`
- **完成情况**：在 `build_overview_markdown` 中对时间戳执行规范化转义 `safe_timestamp = str(timestamp).replace('-', '--').replace(' ', '_').replace(':', '%3A')`，严格遵循 Shields.io 规范（短横杠转义为 `--`，空格转义为 `_`，冒号转义为 `%3A`），彻底解决了此前因日期未转义短横杠导致 Shields.io 徽章服务端解析崩溃返回 `404: badge not found` 的问题；新增 `test_build_overview_shields_badge_escaping` 单元测试全部通过。

### 3.6 源名称 Markdown 转义 [✅ 已完成]
- **涉及文件**：`utils/stats.py` L111-116, `tests/test_stats.py`
- **完成情况**：在 `build_source_stats_markdown` 中对各订阅源名称执行 Markdown 表格语法安全清洗：将可能导致表格列分裂的管道符 `|` 替换为 `-`、破坏行内代码块的反引号 `` ` `` 替换为 `'`，并进一步过滤换行符 `\r\n`；新增 `test_build_source_stats_markdown_safe_escaping` 单元测试覆盖各类非法破坏字符均全部通过。

### 3.7 私有 IP 网段过滤（防 SSRF） [✅ 已完成]
- **涉及文件**：新增 `utils/validators.py`, `core/processor.py` L46-48, `tests/test_validators.py`, `tests/test_processor.py`
- **完成情况**：新增 `utils/validators.py` 专用安全校验模块，引入 `ipaddress` 模块实现 `is_invalid_or_private_server`，系统拦截 RFC 1918 私有网段（`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`）、回环网段（`127.0.0.0/8`, `::1`）、链路本地/云元数据（`169.254.0.0/16`, `fe80::/10`）、运营商 CGNAT（`100.64.0.0/10`）、保留/多播与 IPv6 ULA 网段；成功杜绝了此前混入订阅中的 10 个恶意伪造 `127.0.0.53` 节点；`core/processor.py` 引入该模块保持向下兼容；新增 `test_validators.py` 与 `test_processor.py` 单测全部通过。

### 3.8 协议白名单统一定义 [✅ 已完成]
- **涉及文件**：新增 `utils/constants.py`, `core/fetcher.py` L16, `core/processor.py` L47, L115, `core/parser.py` L5, L44, `tests/test_constants.py`
- **完成情况**：新增 `utils/constants.py` 统一定义 `ALLOWED_PROTOCOLS`、`ALLOWED_TYPES` 与 `CANONICAL_PROTOCOLS`；消除了此前分散在 `fetcher.py`、`processor.py` 和 `parser.py` 各自独立维护的硬编码白名单集合，修复了 `parser.py` 中遗漏 `hy2` 别名协议的隐患，并避免了 `filter_invalid()` 每次循环调用中重新分配集合的开销；新增 `test_constants.py` 单元测试全部通过。

### 3.9 YAML 输出改为 `allow_unicode=True` [✅ 已完成]
- **涉及文件**：`core/generator.py` L414, `tests/test_generator.py`
- **完成情况**：将 `yaml.dump(..., allow_unicode=True)` 启用 Unicode 直出，彻底消除了导出的 `list.meta.yml` 中中文节点名、策略组名称和国旗 Emoji 被强行转义为 `\uXXXX` / `\U0000XXXX` 的问题，生成文件对人类阅读完全友好且降低了文件传输体积；配合已有的 `SafeDumper` 依然严密保护易混淆数字与布尔值；新增针对 Unicode 原生可读导出的单元测试全部通过。

---

## 阶段四：🟢 P3 代码质量与性能优化

### 4.1 消除代码重复 [✅ 已完成]
- **涉及文件**：`utils/common.py`, `utils/constants.py`, `core/parser.py`, `core/processor.py`, `core/generator.py`, `main.py`, `tests/test_common.py`, `tests/test_parser.py`, `tests/test_main.py`
- **完成情况**：
  1. **`deep_sanitize` 统一收敛**：在 `utils/common.py` 统一定义 `deep_sanitize(data, preserve_newlines=False)`，提供严格清洗模式与 YAML 换行保留模式（`preserve_newlines=True`），`core/processor.py` 与 `core/generator.py` 统一复用；
  2. **`parser.py` 类型归一化去重**：移除 `Node.__init__` 在 `isinstance(dict)` 分支中的提前类型归一化与清洗，统一在末尾单点执行 `self.type` 归一化并执行 `self._clean_dict_fields()`；
  3. **VMess cipher 白名单常量提取**：在 `utils/constants.py` 定义 `VMESS_ALLOWED_CIPHERS`，集中用于 `_clean_dict_fields` 与 `_load_vmess`；
  4. **Reality 参数解析复用**：在 `core/parser.py` 提取 `_parse_reality_opts(params)` 辅助方法，Trojan 与 VLESS 协议统一调用；
  5. **私有源解析与标记去重**：在 `main.py` 提取 `_normalize_private_sources(data)`，统一负责对 List/Dict 结构的解包并自动注入 `is_private=True` 标记；
  6. **消除冗余字典映射构建**：在 `core/generator.py` 删除重复构建的 `node_obj_map = {n.name: n for n in nodes}`，全流程复用前面已建好的 `name_to_node`，节约 O(N) 内存与开销；
  7. 全量补充单元测试（共 69 个测试），测试全部通过。

### 4.2 性能优化 [✅ 已完成]
- **涉及文件**：`core/parser.py`, `core/processor.py`, `core/generator.py`, `core/fetcher.py`, `tests/test_parser.py`, `tests/test_processor.py`, `tests/test_fetcher.py`
- **完成情况**：
  1. **节点唯一指纹属性级缓存**：在 `Node` 类中引入 `_identity_cache` 属性，`get_identity()` 计算一次后自动缓存，大幅削减大批量去重时的重复字符串拼接与计算开销；
  2. **循环内正则编译模块级提升**：将 `processor.py` 节点清洗中的孤立标点剥离正则提升为模块级预编译常量 `STRIP_PUNCT_REGEX`，免除循环内频繁正则 lookup 开销；
  3. **未识别地区二次全库扫描消除**：`processor.py` 对未匹配地区的节点同样持久化 `node.data['_region'] = None`，`generator.py` 直接判断 `'_region' in node.data`，彻底避免下游几百甚至数千个未匹配地区节点再次触发全库关键词循环匹配；
  4. **大文件 HTML 嗅探前缀切片优化**：`fetcher.py` 针对 HTML 网页检测改为 `content[:1000].upper()` 切片，避免万行大文件全文复制消耗多兆内存；
  5. **纯链接 / Base64 跳过 YAML 冗余解析**：`fetcher.py` 增加 `proxies:`、`Proxy:`、`payload:` 及 `(server: and port:)` 快速预检，纯链接文本直接绕过耗时的 `yaml.safe_load`；
  6. **移除多余的地区键排序**：删除 `core/generator.py` 中 `active_keys.sort()`，原生复用 Python 3.7+ 字典按 `REGIONS_DB` 既定插入顺序保留的稳定优先级；
  7. 补充对应各项单元测试（测试总数提升至 74 项），全量测试全部通过。

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
