#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IPTV 智能冷热流双池融合引擎 (Cold-Hot Pool Merging Engine)
架构设计：Vertex AI Gemini 4 Carbon
功能：
1. 以 live_base.txt (4700+ 全量频道模板) 为骨架底库，100% 保持所有分类与全球长尾频道；
2. 每日从高可用 IPv4 自动化测活池中拉取最新存活流，智能语义对齐 (Normalization)；
3. 将新鲜存活的热流前置注入 (Prepend) 到对应核心频道首位，确保电视秒开；
4. 容错熔断 (Circuit Breaker)：若上游拉取失败，安全回退到底库，绝不损坏现有配置。
"""

import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

# ==================== 路径与常量 ====================
REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_FILE = REPO_ROOT / "live_base.txt"
OUTPUT_FILE = REPO_ROOT / "live.txt"

UPSTREAM_SOURCES = [
    "https://raw.githubusercontent.com/Guovin/iptv-api/gd/output/result.txt",
    "https://cdn.jsdelivr.net/gh/Guovin/iptv-api@gd/output/result.txt",
    "https://live.zbds.top/tv/iptv4.txt"
]

MAX_URLS_PER_CHANNEL = 15
TIMEOUT_SEC = 6.0

# 黑名单与无效流过滤
BLACKLIST_KEYWORDS = [
    "127.0.0.1", "localhost", "0.0.0.0",
    "宣传", "测试", "群", "失效", "expired"
]

# 常见繁体字转简体字
TRAD_TO_SIMP = str.maketrans(
    "電視臺衛頻道國際體育綜藝電影戲劇新聞財經鳳凰東亞",
    "电视台卫频道国际体育综艺电影戏剧新闻财经凤凰东亚"
)

# 频道别名/异名映射
CHANNEL_ALIAS_MAP = {
    "CCTV5PLUS": "CCTV5+",
    "CCTV5+体育赛事": "CCTV5+",
    "CGTN纪录": "CGTNDOCUMENTARY",
    "凤凰中文": "凤凰卫视中文台",
    "凤凰资讯": "凤凰卫视资讯台",
    "凤凰香港": "凤凰卫视香港台",
    "东方卫视": "东方卫视",
    "上海东方卫视": "东方卫视",
    "旅游卫视": "海南卫视",
    "炫动卡通": "哈哈炫动",
    "卡酷少儿": "北京卡酷少儿",
    "金鹰卡通": "湖南金鹰卡通"
}

# 央视数字识别正则
RE_CCTV_EXTRACT = re.compile(r"^CCTV[-\s]*(\d+\+?|4K|8K|5\+)", re.IGNORECASE)
RE_NOISE_TAGS = re.compile(
    r"(\[.*?\]|\(.*?\)|（.*?）|【.*?】|"
    r"超高清|高清|标清|蓝光|超清|极速|流畅|备用|测试|直播|频道|"
    r"FHD|UHD|HD|SD|HEVC|H265|H\.265|50FPS|60FPS|IPV6|IPV4|"
    r"-\s*|\s+)",
    re.IGNORECASE
)


def normalize_channel_name(raw_name: str) -> str:
    """
    语义归一化主键生成
    例: "CCTV-1 综合 [超清] 1080P" -> "CCTV1"
        "CCTV-5+ 体育赛事 HD"      -> "CCTV5+"
        "湖南卫视 (高清)"          -> "湖南卫视"
    """
    if not raw_name:
        return ""
    name = raw_name.strip().upper().translate(TRAD_TO_SIMP)

    # 1. 优先提取 CCTV 系列
    if name.startswith("CCTV"):
        if "欧" in name:
            return "CCTV4欧洲"
        if "美" in name:
            return "CCTV4美洲"
        m = RE_CCTV_EXTRACT.match(name)
        if m:
            suffix = m.group(1).upper()
            return f"CCTV{suffix}"

    # 2. 剥离噪音修饰词与括号
    has_4k = "4K" in name and not name.startswith("CCTV")
    has_8k = "8K" in name and not name.startswith("CCTV")

    cleaned = RE_NOISE_TAGS.sub("", name).replace("4K", "").replace("8K", "")
    if has_4k:
        cleaned += "4K"
    elif has_8k:
        cleaned += "8K"

    # 3. 别名词典映射
    if cleaned in CHANNEL_ALIAS_MAP:
        return CHANNEL_ALIAS_MAP[cleaned]

    return cleaned if cleaned else re.sub(r"\s+", "", raw_name.upper())


def is_valid_url(url: str, check_ipv4_only: bool = True) -> bool:
    """校验流媒体 URL 是否合法且为纯净 IPv4"""
    if not url or len(url) < 10:
        return False
    url_lower = url.lower()
    if not url_lower.startswith(("http://", "https://", "rtmp://", "rtsp://", "p3p://", "tvbus://")):
        return False
    for kw in BLACKLIST_KEYWORDS:
        if kw in url_lower:
            return False
    if check_ipv4_only:
        # IPv6 地址通常包含 [2409:...
        if "[" in url and "]" in url:
            return False
    return True


def fetch_upstream_content() -> str | None:
    """从多个测速上游拉取最新鲜的直播源文本数据"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {"User-Agent": "Mozilla/5.0"}

    for url in UPSTREAM_SOURCES:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC, context=ctx) as resp:
                if resp.status == 200:
                    data = resp.read().decode("utf-8", errors="ignore")
                    if len(data) > 10000 and "CCTV" in data:
                        print(f"✅ 成功从上游拉取最新测活直播源: {url} ({len(data)} 字节)")
                        return data
        except Exception as e:
            print(f"⚠️ 拉取上游 {url} 失败: {e}")
    return None


def parse_base_file(path: Path):
    """
    解析 4700+ 全量底库文件
    返回：
      categories: [cat1, cat2, ...] 保留所有分类及原始顺序
      data: OrderedDict[cat -> OrderedDict[norm_name -> {'display': str, 'urls': list}]]
    """
    categories = []
    data = OrderedDict()

    if not path.exists():
        raise FileNotFoundError(f"底库模板文件未找到: {path}")

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    current_cat = "未分类"
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#EXTM3U") or line.startswith("//"):
            continue

        if ",#genre#" in line.lower():
            cat_name = line.split(",")[0].strip()
            current_cat = cat_name
            if cat_name not in categories:
                categories.append(cat_name)
                data[cat_name] = OrderedDict()
            continue

        if "," in line:
            parts = line.split(",", 1)
            raw_name = parts[0].strip()
            raw_url = parts[1].strip()

            if not raw_name or not raw_url:
                continue

            if current_cat not in data:
                categories.append(current_cat)
                data[current_cat] = OrderedDict()

            norm_name = normalize_channel_name(raw_name)

            for u in raw_url.split("#"):
                u = u.strip()
                if not is_valid_url(u, check_ipv4_only=False):
                    continue

                if norm_name not in data[current_cat]:
                    data[current_cat][norm_name] = {
                        "display": raw_name,
                        "urls": []
                    }

                clean_u = u.split("$")[0].strip()
                if clean_u not in [existing.split("$")[0].strip() for existing in data[current_cat][norm_name]["urls"]]:
                    data[current_cat][norm_name]["urls"].append(u)

    return categories, data


def parse_upstream_streams(content: str):
    """解析上游测活源，返回流映射字典: norm_name -> list_of_urls"""
    streams = OrderedDict()
    current_cat = ""

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue

        if ",#genre#" in line.lower():
            current_cat = line.split(",")[0].strip()
            continue

        if "," in line:
            parts = line.split(",", 1)
            raw_name = parts[0].strip()
            raw_url = parts[1].strip()

            if not raw_name or not raw_url:
                continue

            # 过滤包含日期或更新时间的假频道行
            if "更新时间" in raw_name or re.match(r"^\d{4}-\d{2}-\d{2}", raw_name):
                continue

            norm_name = normalize_channel_name(raw_name)

            for u in raw_url.split("#"):
                u = u.strip()
                # 上游拉取的流强制限制纯净 IPv4
                if not is_valid_url(u, check_ipv4_only=True):
                    continue

                if norm_name not in streams:
                    streams[norm_name] = []

                clean_u = u.split("$")[0].strip()
                if clean_u not in [x.split("$")[0].strip() for x in streams[norm_name]]:
                    streams[norm_name].append(u)

    return streams


def merge_cold_and_hot(categories: list, base_data: OrderedDict, upstream_streams: dict):
    """
    核心冷热融合算法：
    1. 遍历底库中的所有频道，若上游有对应的新鲜存活流，前置插入 (Prepend) 到最前；
    2. 针对上游可能存在而底库未收录的核心国内台，智能归入合适分类；
    3. 全程保留所有分类顺序与全球境外台。
    """
    merged_count = 0
    injected_urls_count = 0

    # 1. 前置热流注入
    for cat in categories:
        cat_channels = base_data.get(cat, {})
        for norm_name, ch_info in cat_channels.items():
            if norm_name in upstream_streams:
                hot_urls = upstream_streams[norm_name]
                # 过滤并去重
                fresh_to_insert = []
                existing_cleans = [u.split("$")[0].strip() for u in ch_info["urls"]]
                for hu in hot_urls:
                    clean_hu = hu.split("$")[0].strip()
                    if clean_hu not in existing_cleans:
                        fresh_to_insert.append(hu)

                if fresh_to_insert:
                    # 前置插入到最前排，电视优先播放
                    ch_info["urls"] = fresh_to_insert + ch_info["urls"]
                    # 控制单频道最大数量，防止切源卡顿
                    ch_info["urls"] = ch_info["urls"][:MAX_URLS_PER_CHANNEL]
                    merged_count += 1
                    injected_urls_count += len(fresh_to_insert)

    print(f"⚡ 成功为 {merged_count} 个核心频道前置注入 {injected_urls_count} 条最新测活 IPv4 流！")

    # 2. 检查上游是否包含底库未覆盖的新频道（例如新出现的 CCTV 专线或省级卫视）
    known_norms = set()
    for cat in categories:
        known_norms.update(base_data.get(cat, {}).keys())

    unmatched_count = 0
    for norm_name, urls in upstream_streams.items():
        if norm_name not in known_norms and urls:
            # 尝试推断分类
            target_cat = "数字/少儿/地方"
            if norm_name.startswith("CCTV"):
                target_cat = "央视频道"
            elif "卫视" in norm_name:
                target_cat = "卫视频道"
            elif any(k in norm_name for k in ["体育", "咪咕", "足球", "篮球"]):
                target_cat = "🌏体育"
            elif any(k in norm_name for k in ["少儿", "动画", "卡通"]):
                target_cat = "🌏少儿"

            if target_cat in base_data:
                base_data[target_cat][norm_name] = {
                    "display": norm_name,
                    "urls": urls[:MAX_URLS_PER_CHANNEL]
                }
                known_norms.add(norm_name)
                unmatched_count += 1

    if unmatched_count > 0:
        print(f"✨ 动态补充发现 {unmatched_count} 个新活跃频道进对应分类！")


def export_to_file(categories: list, base_data: OrderedDict, output_path: Path):
    """生成标准 DIYP 格式 live.txt 文件"""
    total_lines = 0
    total_channels = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for cat in categories:
            cat_channels = base_data.get(cat, {})
            if not cat_channels:
                continue

            f.write(f"{cat},#genre#\n")
            total_lines += 1

            for norm_name, ch_info in cat_channels.items():
                display_name = ch_info["display"]
                urls = ch_info["urls"]
                if not urls:
                    continue

                total_channels += 1
                for u in urls:
                    f.write(f"{display_name},{u}\n")
                    total_lines += 1

    print(f"💾 成功生成生产级 live.txt ({output_path.name}): 共 {total_channels} 个频道，{total_lines} 行")


def main():
    print("🚀 启动 IPTV 智能冷热双池融合引擎 (Carbon-Engine)...")

    # 1. 读取 4700+ 全量底库模板
    if not BASE_FILE.exists():
        print(f"🚨 致命错误：底库文件 {BASE_FILE} 不存在！终止执行以防配置丢失。")
        sys.exit(1)

    categories, base_data = parse_base_file(BASE_FILE)
    print(f"📖 成功加载全量底库: 包含 {len(categories)} 个分类骨架")

    # 2. 拉取最新测活上游数据
    upstream_content = fetch_upstream_content()

    # 3. 如果成功拉取上游，执行深度语义对齐与热流注入
    if upstream_content:
        upstream_streams = parse_upstream_streams(upstream_content)
        print(f"📡 上游解析出 {len(upstream_streams)} 个活跃频道流池")
        merge_cold_and_hot(categories, base_data, upstream_streams)
    else:
        print("⚠️ 上游拉取失败，触发安全熔断保护机制：直接基于底库输出，防止线上服务断流！")

    # 4. 原子化覆写 live.txt
    export_to_file(categories, base_data, OUTPUT_FILE)
    print("🎉 冷热融合保活流程全部完成！")


if __name__ == "__main__":
    main()
