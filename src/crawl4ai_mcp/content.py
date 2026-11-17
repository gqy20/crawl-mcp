"""正文质量判定、清洗与错误分类

三件事：
  1. JS 壳识别 —— 快速提取偶尔只拿到 "JavaScript is disabled" 这类占位提示，
     长度超过阈值会被误判为成功，必须单独识别
  2. 正文清洗 —— 去掉链接定义块、短导航行、固定 boilerplate，压缩空行
  3. 错误分类 —— 把各种失败原因归一成稳定的 error_code，调用方据此决定重试策略
"""

import re

# ── JS 壳 ──────────────────────────────────────────────────────

JS_SHELL_PATTERNS = [
    r"javascript is disabled",
    r"please enable javascript",
    r"enable javascript to",
    r"this site requires javascript",
    r"you need to enable javascript",
    r"请开启\s*javascript",
    r"需要启用\s*javascript",
]

_JS_SHELL_RE = re.compile("|".join(JS_SHELL_PATTERNS), re.IGNORECASE)


def looks_like_js_shell(text: str) -> bool:
    """内容是否只是"需要开启 JS"的占位提示

    两个条件同时成立才判定：整体很短（≤800 字），且提示语出现在开头 300 字内。
    长文章里顺带提到 "enable javascript" 属于正常正文，不受影响。
    """
    if not text or len(text) > 800:
        return False
    return bool(_JS_SHELL_RE.search(text[:300]))


# ── 清洗 ──────────────────────────────────────────────────────

# 链接定义块：[1]: https://example.com/...
_LINK_DEF_RE = re.compile(r"^\[.+\]:\s*https?://\S+\s*$")
# 短导航行：[首页][12]（链接文字 ≤12 字，长于此视为正文/参考文献，保留）
_SHORT_LINK_RE = re.compile(r"^\[.{1,12}\]\[\d+\]\s*$")

BOILERPLATE_PHRASES = [
    "skip to main content",
    "skip to content",
    "advertisement",
    "accept all cookies",
    "cookie settings",
    "privacy policy",
    "terms of service",
    "all rights reserved",
    "enable javascript",
    "javascript is disabled",
]


def _is_boilerplate(line: str) -> bool:
    """整行都是导航/声明类固定短语"""
    if len(line) > 80:
        return False
    low = line.lower()
    return any(p in low for p in BOILERPLATE_PHRASES)


def clean_markdown(text: str) -> str:
    """清洗 Markdown：去链接定义、短导航行、boilerplate，压缩空行

    只动确定无用的部分，保留列表、表格、标题等正文结构。
    """
    if not text:
        return text

    out: list[str] = []
    blank = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            blank = True
            continue

        if blank and out:
            out.append("")  # 连续空行压缩成一个
        blank = False

        if _LINK_DEF_RE.match(stripped):
            continue
        if _SHORT_LINK_RE.match(stripped):
            continue
        if _is_boilerplate(stripped):
            continue

        out.append(line)

    # 去掉首尾空行
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()

    return "\n".join(out)


# ── 错误分类 ──────────────────────────────────────────────────

# 顺序敏感：越具体的模式越靠前。
# "script_heavy_shell" 排在 empty_content 前面：页面只是 JS 壳（换浏览器/换路径有用），
# 和「服务端真的返回空内容」（HTTP 200 空模板，重试没用）要区分开。
_ERROR_RULES = [
    (
        "js_challenge",
        (r"cloudflare.*challenge", r"js challenge", r"script_heavy_shell"),
    ),
    ("empty_content", (r"near-empty", r"no_content_elements", r"minimal_text")),
    ("antibot", (r"anti-bot", r"antibot", r"blocked by")),
    ("http_403", (r"\b403\b",)),
    ("http_404", (r"\b404\b",)),
    ("http_401", (r"\b401\b",)),
    ("rate_limited", (r"\b429\b", r"too many requests")),
    ("http_5xx", (r"\b5\d\d\b",)),
    ("tls_error", (r"certificate", r"ssl", r"tls")),
    ("timeout", (r"timed out", r"timeout")),
    ("connection_refused", (r"connection refused",)),
    ("connection_reset", (r"connection reset", r"network changed")),
    ("dns_error", (r"could not resolve", r"name or service not known")),
    ("no_results", (r"no results found",)),
]


def classify_error(error: str | None) -> str | None:
    """把错误文本归一成稳定的 error_code；成功时返回 None"""
    if not error:
        return None
    low = error.lower()
    for code, patterns in _ERROR_RULES:
        if any(re.search(p, low) for p in patterns):
            return code
    return "unknown"


# ── 处置建议 ──────────────────────────────────────────────────
#
# error_code 告诉机器「什么坏了」，这里告诉人「下一步该干嘛」。
# 区分标准：换个方式有用（403 / js_challenge / rate_limited）
#          vs 重试没用（404 / empty_content / tls_error）

_ACTIONS = {
    "http_404": "路径可能已失效，换入口页或用搜索重新定位详情页",
    "http_403": "被服务端拒绝，换数据源或改用 Cloud 兜底（不同出口）",
    "http_401": "需要认证，公开页面不该出现，检查 URL 是否指向私有资源",
    "antibot": "被反爬拦截，换出口（Cloud 兜底）或找官方 API",
    "js_challenge": "页面需要 JS 渲染：改走浏览器路径，或换同站详情页/官方 API 源",
    "empty_content": "服务端返回空内容，重试无用，换同站其他页面",
    "rate_limited": "被限速，退避后重试或降低并发",
    "http_5xx": "服务端故障，稍后重试",
    "tls_error": "本机证书链问题，检查系统 ca-certificates（不是站点的问题）",
    "timeout": "超时，可加大超时或稍后重试",
    "connection_refused": "连接被拒，检查目标地址和网络",
    "connection_reset": "连接被重置，网络抖动或被限流，稍后重试",
    "dns_error": "域名解析失败，检查 URL 是否写错",
    "no_results": "没搜到，换关键词或区域",
}


def suggest_action(error_code: str | None) -> str:
    """给 error_code 一句可执行的建议；没有对应建议时返回空串"""
    return _ACTIONS.get(error_code or "", "")


# ── 降级决策用的错误分组 ──────────────────────────────────────
#
# 降级链路是 fast → Cloud → browser，但三跳不是每次都值得走完。
# 按「这个错误换个方式还有没有用」分组，省掉没意义的等待。

#: 确定性失败：换出口、换引擎、换路径都一样，不必再降级
TERMINAL_CODES = frozenset({"http_404", "http_401"})

#: 本机网络/解析问题：Cloud 是云端出口，值得一试；
#: 但本地浏览器用的是同一条网络，大概率同样失败，不必再等一轮浏览器
LOCAL_ONLY_CODES = frozenset({"dns_error", "connection_refused"})

#: 短期粘性：挑战/封禁通常几分钟内不会变，缓存住省得每次重走整条链路
STICKY_CODES = frozenset({"js_challenge", "antibot"})

#: 可以进负缓存的错误（确定性失败 + 短期粘性）
NEGATIVE_CACHE_CODES = TERMINAL_CODES | STICKY_CODES | {"empty_content"}

#: 可以记进「域名记忆」的错误：只有确定性失败才污染域名，
#: 超时/限速这类波动不能算在域名头上
DOMAIN_MEMORY_CODES = TERMINAL_CODES | {"empty_content"}
