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
