#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Curated & Speed-Verified IPTV Pipeline (ZH / EN / JP / KR + Global FAST)
- Combines existing live.txt (untouched) with selected FAST playlists
- Filters strictly to ZH / EN / JP / KR and removes low-quality / shopping / religious / radio / ambient junk
- Deduplicates across sources and selects top candidates per channel
- Launches an isolated temporary read-only Mihomo multi-region probe daemon on router-side (192.168.2.71)
- Tests real HLS manifest + resolution + media playlist + first video segment throughput across candidate routes
- Resolves per-host OpenClash routes (DIRECT / US VPS / regional groups) with zero route conflicts
- Outputs curated live_plus.txt + OpenClash rule-provider YAML bundle + probe report JSON
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from collections import Counter, OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from merge_live import normalize_channel_name  # noqa: E402

INPUT_LIVE = REPO_ROOT / "live.txt"
OUTPUT_LIVE_PLUS = REPO_ROOT / "live_plus.txt"
DEFAULT_OUT_DIR = Path(
    "/Users/tim/.gemini/antigravity/brain/42b3f1c6-8e4b-4f89-a452-1e578a6826d5/scratch/openclash_tv_rules"
)

ROUTER_HOST = "router-side"
ROUTER_IP = "192.168.2.71"
VPS_HOST = "zgo-la"
UA = "Mozilla/5.0 (Linux; Android 9; BRAVIA 4K GB) AppleWebKit/537.36"

PROBE_PORTS = {
    "direct": 17901,
    "us": 17902,
    "uk": 17903,
    "jp": 17904,
    "tw": 17905,
    "hk": 17906,
    "sg": 17907,
    "kr": 17908,
    "ca": 17909,
}

TARGET_CATEGORIES = [
    "央视频道",
    "卫视频道",
    "中文数字/少儿/地方",
    "港澳台",
    "新马华语",
    "日本频道",
    "韩国频道",
    "欧美新闻财经",
    "欧美电影剧集",
    "欧美纪录探索",
    "欧美体育",
    "欧美娱乐少儿音乐",
]

FAST_SOURCES = [
    ("LG US", "https://www.apsattv.com/uslg.m3u", "us", None),
    ("LG UK", "https://www.apsattv.com/gblg.m3u", "uk", None),
    ("LG CA", "https://www.apsattv.com/calg.m3u", "ca", None),
    # LG FR and LG DE intentionally excluded (non-ZH/EN/JP/KR)
    (
        "Samsung TV Plus",
        "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/refs/heads/main/playlists/samsungtvplus_all.m3u",
        None,
        {"United States", "United Kingdom", "Canada", "South Korea"},
    ),
    (
        "Roku",
        "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/refs/heads/main/playlists/roku_all.m3u",
        "us",
        None,
    ),
    (
        "Xumo",
        "https://raw.githubusercontent.com/BuddyChewChew/xumo-playlist-generator/refs/heads/main/playlists/xumo_playlist.m3u",
        "us",
        None,
    ),
    ("Local NOW", "https://www.apsattv.com/localnow.m3u", "us", None),
    (
        "Plex",
        "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/refs/heads/main/playlists/plex_all.m3u",
        None,
        {"United States", "United Kingdom", "Canada", "Australia", "NZ"},
    ),
    (
        "Pluto TV",
        "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/refs/heads/main/playlists/plutotv_all.m3u",
        None,
        {"United States", "United Kingdom", "Canada", "Australia", "New Zealand", "Japan", "South Korea"},
    ),
]

DROP_LIVE_CATEGORIES = {
    "🌏东南亚",
    "🌏法国",
    "🌏德语区",
    "🌏南欧",
    "🌏北欧/荷兰",
    "🌏俄语",
    "🌏中东",
    "🌏南亚",
    "🌏拉美",
}

RE_NON_TARGET_SCRIPT = re.compile(
    r"[\u0400-\u04FF\u0600-\u06FF\u0750-\u077F\u0900-\u097F\u0980-\u09FF"
    r"\u0A00-\u0A7F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F"
    r"\u0D00-\u0D7F\u0E00-\u0E7F\u0590-\u05FF\u0370-\u03FF]"
)

RE_NON_TARGET_LANG_KW = re.compile(
    r"(\b(español|espanol|latino|latam|latin\s*america|south\s*america|telemundo|univision|estrella|deportes|"
    r"noticias|novelas|peliculas|películas|turkiye|türkiye|czech|czechia|slovakia|"
    r"polska|polish|hungary|magyar|ukraine|adria|serbia|romania|romana|bulgaria|"
    r"greece|greek|hindi|tamil|telugu|punjabi|urdu|bengali|gujarati|malayalam|"
    r"marathi|bhojpuri|bangla|assam|asom|sindhi|kannada|arabic|arabiya|mubasher|"
    r"persia|persiana|farsi|kurdish|nederlands|svenska|norsk|dansk|suomi|"
    r"vietnamese|tagalog|filipino|indonesian|hispanic|italiano|português|"
    r"portugues|brasil|deutsch|deutsche|français|francais|french|german|"
    r"russian|russia|cis|egypt|mexico|colombia|argentina|chile|peru|venezuela|"
    r"ecuador|bolivia|paraguay|uruguay|india|bharat|kolkata|delhi|mumbai|punjab|"
    r"gujarat|kerala|bihar|odisha|bengal|chhattisgarh|pradesh|karnataka|telangana|"
    r"kashmir|pakistan|bangladesh|nepal|sri\s*lanka|ananda|ndtv|georgia|balkan|"
    r"crimea|cherniveckiy|belarus|kazakh|uzbek|azerbaijan|armenia|moldova|albania|"
    r"croatia|slovenia|bosnia|macedonia|estonia|latvia|lithuania|mongolia)\b|"
    r"\b(zee|abp)\s+[a-z]|"
    r"\bCine\b(?![\w])|en español|\(fr\)|\(de\)|\(es\)|\(pt\)|\(it\)|"
    r"\bSK\b|法语|德语|俄语|阿拉伯|西班牙|葡萄牙|泰语|越南|印地|"
    r"塞尔维亚|乌克兰|意大利|荷兰|北欧|希腊|土耳其|波兰|捷克|匈牙利|罗马尼亚|"
    r"缅甸|柬埔寨|老挝|尼泊尔|巴基斯坦|孟加拉|伊朗|以色列|蒙古)",
    re.IGNORECASE,
)

RE_SHOPPING = re.compile(
    r"(\bqvc\b|\bhsn\b|shophq|shoplc|\bjtv\b|jewelry|jewellery|gemstv|"
    r"shopping|shop\s*channel|cj\s*onstyle|gsshop|gstv|home\s*shopping|\+shop\b|"
    r"lotte\s*one|sk\s*stoa|kt\s*alpha|gs\s*my|신세계쇼핑|공영쇼핑|현대홈|홈앤쇼핑|홈쇼핑|쇼핑|"
    r"ショップチャンネル|购物|导购|优购|好享购|风尚购物|家有购物|东方购物|"
    r"快乐购|中视购物|环球购物|央广购物)",
    re.IGNORECASE,
)

RE_RELIGIOUS = re.compile(
    r"(\btbn\b|daystar|3abn|ewtn|\bcbn\b|sonlife|hope\s*channel|\bfaith\b|"
    r"gospel|church|catholic|bible|\bpraise\b|god\s*tv|god's|inspiration\s*tv|"
    r"juce\s*tv|hillsong|islam|quran|\bdeen\b|sikh|buddhist|btn\s*tv|cgntv|"
    r"好消息|大爱|人间卫视|慈济|华藏|宗教|佛)",
    re.IGNORECASE,
)

RE_RADIO = re.compile(
    r"(\bradio\b|bbc\s+asian\s+network|iheart|\bfm\b|\bam\s+news|广播|电台)",
    re.IGNORECASE,
)

RE_JUNK_FILLER = re.compile(
    r"(fireplace|yule\s*log|holidayscapes|ambience|ambient\b|puppy|cat\s*tv|dog\s*tv|"
    r"5-minute\s*crafts|city\s*of\s+|county\s*of\s+|public\s*access|\bpeg\b|"
    r"legislative|accessvision|\bcmac\b|\bcan\s*tv|civic\s*channel|board\s*of\s+|"
    r"醉美沙滩|莲花山顶|景区|慢直播|测试|宣传|失效|aquarium|trains?\s*24)",
    re.IGNORECASE,
)

RE_CN_JUNK_HOST = re.compile(r"(127\.0\.0\.1|localhost|0\.0\.0\.0)", re.IGNORECASE)

# Hosts that MUST NEVER be emitted into narrow TV rule-providers
SAFETY_EXCLUDED_DOMAINS = {
    "google.com",
    "googleapis.com",
    "googlevideo.com",
    "youtube.com",
    "youtu.be",
    "github.com",
    "githubusercontent.com",
    "apple.com",
    "icloud.com",
    "openai.com",
    "chatgpt.com",
    "anthropic.com",
    "claude.ai",
    "netflix.com",
    "nflxvideo.net",
    "disneyplus.com",
    "cloudflare.com",
    "cloudfront.net",
    "akamaized.net",
    "akamaihd.net",
    "amazonaws.com",
    "fastly.net",
    "jsdelivr.net",
    "cdn.jsdelivr.net",
    "fastly.jsdelivr.net",
    "trimmy.top",
    "ipinfo.io",
}

ZH_EXTRA_ALIASES = {
    "TVBSASIA": "TVBS亚洲",
    "TVBS亚洲台": "TVBS亚洲",
    "中天新闻": "中天新闻台",
    "东森新闻": "东森新闻台",
    "民视新闻": "民视新闻台",
    "台视新闻": "台视新闻台",
    "三立新闻": "三立新闻台",
    "翡翠台": "TVB翡翠台",
    "无线翡翠台": "TVB翡翠台",
    "明珠台": "TVB明珠台",
    "无线明珠台": "TVB明珠台",
    "无线星河": "TVB星河",
    "凤凰卫视中文台": "凤凰中文",
    "凤凰中文台": "凤凰中文",
    "凤凰卫视资讯台": "凤凰资讯",
    "凤凰资讯台": "凤凰资讯",
    "凤凰卫视香港台": "凤凰香港",
    "凤凰香港台": "凤凰香港",
    "CCTV第一剧场": "第一剧场",
    "CCTV风云剧场": "风云剧场",
    "CCTV怀旧剧场": "怀旧剧场",
    "CCTV风云足球": "风云足球",
    "CCTV风云音乐": "风云音乐",
    "CCTV高尔夫网球": "高尔夫网球",
    "CCTV女性时尚": "女性时尚",
    "CCTV兵器科技": "兵器科技",
    "CCTV世界地理": "世界地理",
    "CCTV央视文化精品": "文化精品",
    "CCTV文化精品": "文化精品",
    "CCTV卫生健康": "卫生健康",
    "CCTV-9": "CCTV9",
    "CCTV-2": "CCTV2",
    "CCTV-7": "CCTV7",
    "NEWK-POP": "NEWKPOP",
    "ARIRANGTV": "ARIRANG",
    "ARIRANGWORLD": "ARIRANG",
}

RE_CJK = re.compile(r"[\u4e00-\u9fff]")
RE_JP_KANA = re.compile(r"[\u3040-\u30ff]")
RE_KR_HANGUL = re.compile(r"[\uac00-\ud7af]")


def is_ip_host(host: str) -> bool:
    h = host.split(":", 1)[0].strip("[]")
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def strip_port(netloc: str) -> str:
    if netloc.startswith("["):
        return netloc
    return netloc.split(":", 1)[0].lower().strip()


def clean_lg_macro_url(url: str) -> str | None:
    """Strip unencoded [...] or {...} macro query params so ExoPlayer/TVBox can parse the URI."""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        return None
    parsed = urllib.parse.urlsplit(u)
    if "[" in parsed.netloc or "]" in parsed.netloc or "[" in parsed.path or "{" in parsed.path:
        return None
    if "[" in parsed.query or "]" in parsed.query or "{" in parsed.query or "}" in parsed.query:
        kept_q = []
        for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            if any(ch in k or ch in v for ch in "[]{}"):
                continue
            kept_q.append((k, v))
        new_query = urllib.parse.urlencode(kept_q)
        u = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment))
    if any(ch in u for ch in "[]{}"):
        return None
    return u


def clean_display_name(raw_name: str, is_lg: bool = False) -> str:
    name = raw_name.replace("\r", "").replace(",", " · ").strip()
    if is_lg:
        name = re.sub(r"^\d{2,4}\s+", "", name).strip()
    return re.sub(r"\s+", " ", name).strip()


def is_junk_channel(name: str, group: str, url: str) -> tuple[bool, str]:
    if not name or not url:
        return True, "empty"
    if not url.lower().startswith(("http://", "https://")):
        return True, "scheme"
    if RE_CN_JUNK_HOST.search(url):
        return True, "localhost"
    # IPv6 literal check
    netloc = urllib.parse.urlsplit(url).netloc
    if netloc.startswith("[") and ":" in netloc:
        return True, "ipv6"

    combo = f"{name} {group}"
    if RE_NON_TARGET_SCRIPT.search(combo):
        return True, "non_target_script"
    if RE_NON_TARGET_LANG_KW.search(combo):
        return True, "non_target_lang"
    host_only = strip_port(netloc)
    if (
        not re.search(r"(TV BRICS Chinese|Telesur English|TVP World|\bCNA\b|\bDW\b|\bBBC\b|\bNHK\b)", name, re.I)
        and (
            re.search(
                r"\.(ru|su|by|kz|ua|cz|ro|pl|hu|bg|rs|hr|si|sk|tr|ir|iq|sa|ae|eg|in|pk|bd|lk|np|th|vn|id|ph|my|br|mx|ar|cl|co|pe|ve|ec|py|uy|bo|es|pt|it|fr|de|nl|be|se|no|dk|fi|gr)$",
                host_only,
            )
            or re.search(
                r"(suprememaster|desdeparaguay|desde-paraguay|haber100|trt\s*haber|\bhaber\b|horoshee\s*kino|indiyskoye\s*kino|nash\s*kinopokaz|\bpro\s*cinema\b|cme-ro|rus-radio|telesur\s+hd|telediario|al\s+araby|obshchestvennoe|finans\s+turk|euronews\s+spanish)",
                f"{name} {url}",
                re.I,
            )
        )
    ):
        return True, "non_target_lang"
    if RE_SHOPPING.search(combo):
        return True, "shopping"
    if RE_RELIGIOUS.search(combo):
        return True, "religious"
    if RE_RADIO.search(name):
        return True, "radio"
    if RE_JUNK_FILLER.search(combo):
        return True, "junk_filler"
    return False, ""


def detect_language_and_canonical(
    name: str, src_name: str, src_cat: str, region_hint: str | None
) -> tuple[str, str]:
    """
    Returns (lang, canonical_key) where lang in {'zh', 'jp', 'kr', 'en'}.
    """
    if src_cat in ("央视频道", "卫视频道", "数字/少儿/地方", "🌏港澳台", "🌏新马"):
        lang = "zh"
    elif src_cat == "🌏日本" or RE_JP_KANA.search(name):
        lang = "jp"
    elif src_cat == "🌏韩国" or region_hint == "kr" or RE_KR_HANGUL.search(name):
        lang = "kr"
    elif "（英语" in name or "(英语" in name:
        lang = "en"
    elif RE_CJK.search(re.sub(r"（.*?）|\(.*?\)", "", name)):
        lang = "zh"
    else:
        lang = "en"

    # Override obvious Japanese / Korean channels sitting in mixed cats
    if re.search(r"^(NHK|TOKYO MX|TBSテレビ|フジテレビ|テレビ朝日|テレビ東京|MBSニュース|FNNプライム|日テレ)", name, re.I):
        lang = "jp"
    elif re.search(r"^(KBS|MBC|SBS|EBS|Arirang|TV Chosun|JTBC|YTN|Channel A|CJ ENM|NEW K-POP)", name, re.I):
        if "MBC America" not in name and "MBC Mood" not in name and "MBC Loud" not in name:
            if src_cat == "🌏韩国" or region_hint == "kr" or re.search(r"^(KBS|EBS|Arirang|TV Chosun|JTBC|YTN|NEW K-POP)", name, re.I):
                lang = "kr"

    if lang == "zh":
        key = normalize_channel_name(name)
        key = ZH_EXTRA_ALIASES.get(key, key)
        return "zh", f"zh:{key}"

    if lang == "jp":
        cleaned = re.sub(r"(\[.*?\]|\(.*?\)|\s+(HD|SD|4K|FHD|TV)\b)", "", name, flags=re.I)
        key = re.sub(r"[\s\-_]+", "", cleaned).upper()
        return "jp", f"jp:{key or name.upper()}"

    if lang == "kr":
        cleaned = re.sub(r"(\[.*?\]|\(.*?\)|\b(HD|SD|FHD|UHD|4K|TV)\b)", "", name, flags=re.I)
        key = re.sub(r"[\s\-_]+", "", cleaned).upper()
        key = ZH_EXTRA_ALIASES.get(key, key)
        return "kr", f"kr:{key or name.upper()}"

    # English canonicalization (merge exact/country variants like Pluto/Samsung/Plex duplicates)
    cleaned = re.sub(r"\[.*?\]|\(.*?\)|【.*?】", "", name)
    cleaned = re.sub(
        r"\b(FHD|UHD|HD|SD|4K|1080P|720P|50FPS|60FPS|IPV4|IPV6|PLUTO\s*TV|SAMSUNG|EAST|WEST)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    alnum = re.sub(r"[^a-z0-9]+", "", cleaned.lower())
    if alnum in ("cbsnews", "cbsnews247", "cbsnewslive"):
        alnum = "cbsnews247"
    elif alnum in ("abcnews", "abcnewslive"):
        alnum = "abcnewslive"
    elif alnum in ("nbcnews", "nbcnewsnow"):
        alnum = "nbcnewsnow"
    elif alnum in ("nhkworld", "nhkworldjapan"):
        return "jp", "jp:NHKWORLDJAPAN"
    return "en", f"en:{alnum or name.lower()}"


def classify_target_category(lang: str, name: str, canonical: str, src_cat: str, fast_group: str, origin_region: str | None) -> str:
    bare = canonical.split(":", 1)[1]
    if lang == "zh":
        if bare.startswith("CCTV") and bare not in ("CCTVWORLDGEOGRAPHY", "CCTVCULTUREOFQUALITY"):
            return "央视频道"
        if "卫视" in bare and not any(k in bare for k in ("凤凰", "东森", "TVBS", "中天", "民视", "台视", "华视", "中视", "三立", "八大", "年代", "非凡", "寰宇", "澳视", "莲花")):
            return "卫视频道"
        if src_cat == "🌏新马" or any(k in bare for k in ("CHANNEL8", "CHANNELU", "CHANNEL5", "8频道", "U频道", "亚洲新闻台", "CNA")):
            if lang == "zh" or src_cat == "🌏新马":
                return "新马华语"
        if src_cat == "🌏港澳台" or any(
            k in bare
            for k in (
                "TVB", "翡翠", "明珠", "凤凰", "中天", "TVBS", "东森", "民视", "台视",
                "中视", "华视", "三立", "八大", "年代", "年代", "非凡", "寰宇", "纬来",
                "龙祥", "星卫", "星河", "华娱", "星空", "NOW", "VIUTV", "HOY", "RTHK",
                "澳视", "澳亚", "公视", "大爱", "大唐", "靖天", "采昌", "美亚", "MEIAH", "ASTRO", "耀才", "TAIWANPLUS",
            )
        ):
            return "港澳台"
        if src_cat == "央视频道":
            return "央视频道"
        if src_cat == "卫视频道":
            return "卫视频道"
        return "中文数字/少儿/地方"

    if lang == "jp":
        return "日本频道"
    if lang == "kr":
        return "韩国频道"

    # English categorization
    combo = f"{name} {fast_group} {src_cat}".lower()
    if src_cat == "🌏国际新闻" or "local now" in name.lower() or any(
        w in combo
        for w in (
            "news", "bloomberg", "cnbc", "cnn", "bbc news", "sky news", "fox business",
            "fox weather", "weather", "reuters", "chedd", "scripp", "livenow", "today all day",
            "euronews", "al jazeera", "cgtn", "cna", "c-span", "cspan", "court tv", "law & crime",
            "yahoo! finance", "finance", "abc news", "nbc news", "cbs news", "60 minutes",
            "dateline", "worldwidenews", "newsnation", "newsmax", "wion", "firstpost", "nhk world", "dw news",
        )
    ):
        return "欧美新闻财经"
    if src_cat == "🌏体育" or any(
        w in combo
        for w in (
            "sport", "espn", "fox sports", "cbs sports", "nbc sports", "nba", "nfl", "mlb",
            "nhl", "ufc", "wwe", "pga", "golf", "tennis", "f1", "racing", "racer", "nascar",
            "soccer", "football", "cricket", "boxing", "mma", "red bull", "fuel tv", "beIN".lower(),
            "willow", "olympic", "man city", "real madrid", "fifa", "poker", "wpt", "billiard",
            "pickleball", "unbeaten",
        )
    ):
        return "欧美体育"
    if src_cat == "🌏纪录片" or any(
        w in combo
        for w in (
            "docu", "history", "national geographic", "nat geo", "discovery", "bbc earth",
            "smithsonian", "curiosity", "science", "nature", "animal", "wildlife", "wild earth",
            "true crime", "crime", "forensic", "unsolved", "cold case", "haunting", "ghost",
            "modern marvels", "magellan", "historyhit", "lovenature", "love nature", "nasa", "military",
            "biography", "a&e", "48 hours", "lockup", "jail", "trublu",
        )
    ):
        return "欧美纪录探索"
    if src_cat == "🌏电影" or any(
        w in combo
        for w in (
            "movie", "cinema", "film", "cinevault", "hallmark", "miramax", "paramount",
            "lionsgate", "sony one", "universal", "warner", "mgm", "axn", "thriller",
            "horror", "sci-fi", "scifi", "western", "action", "drama", "classics", "noir",
            "moviesphere", "grindhouse", "shout", "tcm", "showtime", "starz", "hbo", "rifftrax",
            "mst3k", "stargate", "star trek", "csi", "ncis", "bond", "007", "doctor who",
            "walking dead", "baywatch", "walker", "cheers", "frasier", "south park", "seinfeld",
            "csi:", "criminal minds", "law & order", "addams", "series", "sitcom", "mystery",
        )
    ):
        return "欧美电影剧集"
    return "欧美娱乐少儿音乐"


def fetch_fast_source(src_name: str, url: str) -> str:
    cmd = ["curl", "-g", "-sS", "-L", "--connect-timeout", "5", "-m", "10", "-A", UA, url]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode == 0 and "#EXTM3U" in p.stdout[:300]:
        return p.stdout
    # Fallback via zgo-la if direct fetch (e.g. apsattv.com) times out
    remote_cmd = f"curl -g -sS -L --connect-timeout 8 -m 20 -A '{UA}' '{url}'"
    p2 = subprocess.run(["ssh", "-o", "ConnectTimeout=6", VPS_HOST, remote_cmd], capture_output=True, text=True)
    if p2.returncode == 0 and "#EXTM3U" in p2.stdout[:300]:
        return p2.stdout
    raise RuntimeError(f"Failed to fetch {src_name}: {p.stderr[:120]} / {p2.stderr[:120]}")


def parse_m3u_entries(text: str, src_name: str, default_region: str | None, allowed_groups: set[str] | None):
    is_lg = src_name.startswith("LG ")
    entries = []
    cur_name, cur_group, cur_lang = "", "", ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            mg = re.search(r'group-title="([^"]*)"', line)
            ml = re.search(r'tvg-language="([^"]*)"', line)
            cur_group = mg.group(1).strip() if mg else ""
            cur_lang = ml.group(1).strip() if ml else ""
            mt = re.match(r'^#EXTINF:[^"\n]*(?:"[^"]*"[^"\n,]*)*,(.*)$', line)
            cur_name = mt.group(1).strip() if mt else (line.rsplit(",", 1)[1].strip() if "," in line else "")
        elif line.startswith(("http://", "https://")):
            if allowed_groups is not None and cur_group not in allowed_groups:
                cur_name = ""
                continue
            if src_name == "Local NOW" and (
                "More Cities" in cur_group or "Family and Faith" in cur_group
            ):
                cur_name = ""
                continue
            if cur_lang and not re.search(r"(eng|english|chi|zh|zho|cmn|yue|jpn|ja|kor|ko)", cur_lang, re.I):
                cur_name = ""
                continue

            had_macro = any(ch in line for ch in "[]{}")
            cleaned_url = clean_lg_macro_url(line)
            if not cleaned_url:
                cur_name = ""
                continue
            disp_name = clean_display_name(cur_name, is_lg=is_lg)

            # Determine region hint from group_title
            region = default_region
            gl = cur_group.lower()
            if "united states" in gl or "localnow" in gl:
                region = "us"
            elif "united kingdom" in gl:
                region = "uk"
            elif "canada" in gl:
                region = "ca"
            elif "south korea" in gl or "korea" in gl:
                region = "kr"
            elif "japan" in gl:
                region = "jp"
            elif "australia" in gl or gl == "nz" or "new zealand" in gl:
                region = "au"

            entries.append(
                {
                    "name": disp_name,
                    "group": cur_group,
                    "url": cleaned_url,
                    "source": src_name,
                    "src_cat": "",
                    "region": region,
                    "had_macro": had_macro,
                }
            )
            cur_name = ""
    return entries


def parse_existing_live(path: Path):
    entries = []
    cur_cat = "数字/少儿/地方"
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith(("#EXTM3U", "//")):
            continue
        if ",#genre#" in s.lower():
            cur_cat = s.split(",", 1)[0].strip()
            continue
        if "," not in s:
            continue
        if cur_cat in DROP_LIVE_CATEGORIES:
            continue
        raw_name, raw_urls = s.split(",", 1)
        raw_name = clean_display_name(raw_name)
        for u in raw_urls.split("#"):
            u = u.split("$", 1)[0].strip()
            if not u.startswith(("http://", "https://")):
                continue
            if any(ch in u for ch in "[]{}"):
                # Could be IPv6 literal or broken macro
                continue
            region = None
            if cur_cat == "🌏英国":
                region = "uk"
            elif cur_cat == "🌏美国":
                region = "us"
            elif cur_cat == "🌏加澳新":
                region = "ca"
            elif cur_cat == "🌏日本":
                region = "jp"
            elif cur_cat == "🌏韩国":
                region = "kr"
            elif cur_cat == "🌏港澳台":
                region = "tw"
            elif cur_cat == "🌏新马":
                region = "sg"
            entries.append(
                {
                    "name": raw_name,
                    "group": cur_cat,
                    "url": u,
                    "source": "live.txt",
                    "src_cat": cur_cat,
                    "region": region,
                    "had_macro": False,
                }
            )
    return entries


def candidate_priority_key(item: dict) -> tuple:
    # Prefer: (1) non-macro over originally-macro, (2) existing live.txt domestic/HK-TW, (3) US FAST over UK/CA/AU, (4) clean platform order
    region_rank = {"us": 0, None: 1, "tw": 1, "hk": 1, "jp": 1, "kr": 1, "sg": 1, "uk": 2, "ca": 3, "au": 4}.get(
        item["region"], 5
    )
    src_rank = {
        "live.txt": 0,
        "Pluto TV": 1,
        "Samsung TV Plus": 2,
        "Plex": 3,
        "Xumo": 4,
        "Roku": 5,
        "Local NOW": 6,
        "LG US": 7,
        "LG UK": 8,
        "LG CA": 9,
    }.get(item["source"], 10)
    return (1 if item["had_macro"] else 0, region_rank, src_rank)


def collect_candidates() -> tuple[dict[str, dict], dict]:
    stats = {"raw_counts": {}, "dropped_reasons": Counter(), "lang_counts": Counter()}
    raw_items = []

    live_items = parse_existing_live(INPUT_LIVE)
    stats["raw_counts"]["live.txt(kept_cats)"] = len(live_items)
    raw_items.extend(live_items)

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_fast_source, n, u): (n, r, g) for n, u, r, g in FAST_SOURCES}
        for f in as_completed(futs):
            src_name, def_reg, allowed_g = futs[f]
            try:
                txt = f.result()
                parsed = parse_m3u_entries(txt, src_name, def_reg, allowed_g)
                stats["raw_counts"][src_name] = len(parsed)
                raw_items.extend(parsed)
                print(f"  📥 {src_name:16s}: 解析到 {len(parsed):4d} 条语种合规候选流")
            except Exception as e:
                print(f"  ⚠️ {src_name} 拉取失败: {e}")

    # Filter & group by canonical channel
    channels: dict[str, dict] = OrderedDict()
    seen_urls_global = set()
    for it in raw_items:
        junk, reason = is_junk_channel(it["name"], it["group"], it["url"])
        if junk:
            stats["dropped_reasons"][reason] += 1
            continue
        u_norm = it["url"].strip()
        if u_norm in seen_urls_global:
            stats["dropped_reasons"]["exact_url_dup"] += 1
            continue
        seen_urls_global.add(u_norm)

        lang, canonical = detect_language_and_canonical(
            it["name"], it["source"], it["src_cat"], it["region"]
        )
        cat = classify_target_category(
            lang, it["name"], canonical, it["src_cat"], it["group"], it["region"]
        )
        stats["lang_counts"][lang] += 1

        if canonical not in channels:
            channels[canonical] = {
                "canonical": canonical,
                "display": it["name"],
                "lang": lang,
                "category": cat,
                "candidates": [],
            }
        else:
            # Prefer cleaner display name (without leading numbers or live.txt clean name)
            cur_disp = channels[canonical]["display"]
            if it["source"] == "live.txt" and len(it["name"]) <= len(cur_disp) + 4 and cur_disp.isupper() and not it["name"].isupper():
                channels[canonical]["display"] = it["name"]
            # Upgrade category if more specific
            if it["src_cat"] in ("央视频道", "卫视频道", "港澳台"):
                channels[canonical]["category"] = classify_target_category(
                    lang, it["name"], canonical, it["src_cat"], it["group"], it["region"]
                )
        channels[canonical]["candidates"].append(it)

    # Cap candidates per channel
    total_cands = 0
    for ch in channels.values():
        ch["candidates"].sort(key=candidate_priority_key)
        cap = 15 if ch["category"] in ("央视频道", "卫视频道", "港澳台") else 3
        ch["candidates"] = ch["candidates"][:cap]
        total_cands += len(ch["candidates"])

    stats["unique_channels_pre_probe"] = len(channels)
    stats["candidates_to_probe"] = total_cands
    return channels, stats


def start_router_probe_daemon():
    """Start isolated temporary Mihomo daemon on router-side using cached type:file proxy_providers."""
    ruby_script = r'''
require "yaml"
cfg = YAML.load_file("/etc/openclash/config/smart-lite.yaml")
vps = (cfg["proxies"] || []).find { |p| p["name"] == "US - Los Angeles - Hy2" }
abort("US - Los Angeles - Hy2 not found in smart-lite.yaml") unless vps

groups_src = cfg["proxy-groups"] || []
by_name = {}
groups_src.each { |g| by_name[g["name"]] = g }

def clone_group(src, new_name, fallback_filter)
  g = src ? src.dup : {}
  {
    "name" => new_name,
    "type" => "url-test",
    "include-all" => true,
    "url" => "http://www.gstatic.com/generate_204",
    "interval" => 300,
    "tolerance" => 50,
    "lazy" => false,
    "filter" => g["filter"] || fallback_filter
  }
end

probe_cfg = {
  "allow-lan" => true,
  "bind-address" => "192.168.2.71",
  "ipv6" => false,
  "mode" => "rule",
  "log-level" => "error",
  "unified-delay" => true,
  "tcp-concurrent" => true,
  "find-process-mode" => "off",
  "dns" => {
    "enable" => true,
    "listen" => "127.0.0.1:17953",
    "ipv6" => false,
    "enhanced-mode" => "normal",
    "default-nameserver" => ["223.5.5.5", "119.29.29.29"],
    "nameserver" => ["223.5.5.5", "119.29.29.29"],
    "proxy-server-nameserver" => ["223.5.5.5", "119.29.29.29"]
  },
  "proxies" => [vps],
  "proxy-providers" => {
    "Airport1" => { "type" => "file", "path" => "./proxy_provider/Airport1" },
    "Airport2" => { "type" => "file", "path" => "./proxy_provider/Airport2" },
    "Airport3" => { "type" => "file", "path" => "./proxy_provider/Airport3" }
  },
  "proxy-groups" => [
    clone_group(by_name["英国节点"], "英国节点", "(?=.*(英|伦敦|UK|GB|United Kingdom|Britain|London))"),
    clone_group(by_name["日本节点"], "日本节点", "(?=.*(日|JP|Japan))"),
    clone_group(by_name["台湾节点"], "台湾节点", "(?=.*(台|TW|Taiwan))"),
    clone_group(by_name["香港节点"], "香港节点", "(?=.*(港|HK|Hong))"),
    clone_group(by_name["狮城节点"], "狮城节点", "(?=.*(新|狮|獅|SG|Singapore))"),
    clone_group(nil, "韩国节点", "(?=.*(韩|韓|Korea|KR))(?!.*(特殊|日用|高级|标准|购物|Traffic|Expire|剩余|重置|流量|到期|套餐))"),
    clone_group(nil, "加拿大节点", "(?=.*(加拿大|Canada))(?!.*(新加坡|特殊|日用|高级|标准|购物|Traffic|Expire|剩余|重置|流量|到期|套餐))")
  ],
  "listeners" => [
    { "name" => "in_direct", "type" => "http", "port" => 17901, "listen" => "192.168.2.71" },
    { "name" => "in_us",     "type" => "http", "port" => 17902, "listen" => "192.168.2.71" },
    { "name" => "in_uk",     "type" => "http", "port" => 17903, "listen" => "192.168.2.71" },
    { "name" => "in_jp",     "type" => "http", "port" => 17904, "listen" => "192.168.2.71" },
    { "name" => "in_tw",     "type" => "http", "port" => 17905, "listen" => "192.168.2.71" },
    { "name" => "in_hk",     "type" => "http", "port" => 17906, "listen" => "192.168.2.71" },
    { "name" => "in_sg",     "type" => "http", "port" => 17907, "listen" => "192.168.2.71" },
    { "name" => "in_kr",     "type" => "http", "port" => 17908, "listen" => "192.168.2.71" },
    { "name" => "in_ca",     "type" => "http", "port" => 17909, "listen" => "192.168.2.71" }
  ],
  "rules" => [
    "IN-NAME,in_direct,DIRECT",
    "IN-NAME,in_us,US - Los Angeles - Hy2",
    "IN-NAME,in_uk,英国节点",
    "IN-NAME,in_jp,日本节点",
    "IN-NAME,in_tw,台湾节点",
    "IN-NAME,in_hk,香港节点",
    "IN-NAME,in_sg,狮城节点",
    "IN-NAME,in_kr,韩国节点",
    "IN-NAME,in_ca,加拿大节点",
    "MATCH,DIRECT"
  ]
}

File.write("/tmp/probe-mihomo.yaml", YAML.dump(probe_cfg))
'''
    b64 = base64.b64encode(ruby_script.encode()).decode()
    run_cmd = (
        "Process::GID.change_privilege(65534); "
        "exec('/etc/openclash/clash', '-d', '/tmp/probe-dir', '-f', '/tmp/probe-mihomo.yaml')"
    )
    remote = (
        f"kill $(cat /tmp/probe-mihomo.pid 2>/dev/null) 2>/dev/null || true; "
        f"rm -rf /tmp/probe-dir && mkdir -p /tmp/probe-dir/proxy_provider && "
        f"ln -s /etc/openclash/*.mmdb /etc/openclash/*.dat /tmp/probe-dir/ 2>/dev/null || true; "
        f"cp /etc/openclash/proxy_provider/Airport1 /etc/openclash/proxy_provider/Airport2 /etc/openclash/proxy_provider/Airport3 /tmp/probe-dir/proxy_provider/ && "
        f"echo '{b64}' | base64 -d | ruby && "
        f"chmod -R 777 /tmp/probe-dir /tmp/probe-mihomo.yaml && touch /tmp/probe-mihomo.log && chmod 666 /tmp/probe-mihomo.log && "
        f"/etc/openclash/clash -t -d /tmp/probe-dir -f /tmp/probe-mihomo.yaml && "
        f"(nohup ruby -e \"{run_cmd}\" </dev/null >/tmp/probe-mihomo.log 2>&1 & echo $! > /tmp/probe-mihomo.pid); "
        f"sleep 2; "
        f"kill -0 $(cat /tmp/probe-mihomo.pid) && netstat -tln 2>/dev/null | grep -q 17901 && echo PROBE_STARTED || (cat /tmp/probe-mihomo.log; false)"
    )
    p = subprocess.run(["ssh", "-o", "ConnectTimeout=8", ROUTER_HOST, remote], capture_output=True, text=True)
    if p.returncode != 0 or "PROBE_STARTED" not in p.stdout:
        raise RuntimeError(f"Failed to start probe daemon:\n{p.stdout}\n{p.stderr}")
    time.sleep(3.5)


def stop_router_probe_daemon():
    remote = (
        "kill $(cat /tmp/probe-mihomo.pid 2>/dev/null) 2>/dev/null || true; "
        "rm -rf /tmp/probe-dir /tmp/probe-mihomo.pid /tmp/probe-mihomo.yaml /tmp/probe-mihomo.log"
    )
    subprocess.run(["ssh", "-o", "ConnectTimeout=6", ROUTER_HOST, remote], capture_output=True, text=True)


def smoke_test_probe_ports() -> dict[str, str]:
    """Verify each probe port returns expected exit country."""
    working = {}

    def check_port(kv):
        route, port = kv
        proxy = f"http://{ROUTER_IP}:{port}"
        if route == "direct":
            p = subprocess.run(
                ["curl", "-sS", "-m", "6", "-x", proxy, "http://myip.ipip.net"],
                capture_output=True,
                text=True,
            )
            if p.returncode == 0 and ("中国" in p.stdout or "CN" in p.stdout):
                return route, port, 0, "CN", ""
        p = subprocess.run(
            ["curl", "-sS", "-m", "7", "-x", proxy, "http://ip-api.com/line/?fields=countryCode"],
            capture_output=True,
            text=True,
        )
        code = p.stdout.strip().splitlines()[0].strip() if p.stdout.strip() else ""
        if len(code) != 2:
            p2 = subprocess.run(
                ["curl", "-sS", "-m", "7", "-x", proxy, "https://cloudflare.com/cdn-cgi/trace"],
                capture_output=True,
                text=True,
            )
            m_loc = re.search(r"loc=([A-Z]{2})", p2.stdout)
            if m_loc:
                return route, port, 0, m_loc.group(1), ""
            return route, port, p2.returncode, code, (p.stderr or p2.stderr).strip()
        return route, port, p.returncode, code, p.stderr.strip()

    with ThreadPoolExecutor(max_workers=9) as ex:
        for route, port, rc, country, err in ex.map(check_port, PROBE_PORTS.items()):
            if rc == 0 and len(country) == 2:
                working[route] = country
                print(f"  ✅ 探测端口 {route:6s} (:{port}) -> 出口国家: {country}")
            else:
                print(f"  ⚠️ 探测端口 {route:6s} (:{port}) 不可用: rc={rc} country={country!r} {err[:60]}")
    return working


def fetch_http_prefix(url: str, proxy_url: str, timeout: float = 4.5, max_bytes: int = 204800):
    """Fetch HTTP status, effective URL after redirects, content-type, body prefix up to max_bytes, and wall elapsed."""
    cmd = [
        "curl", "-g", "-k", "-sS", "-L", "--max-redirs", "5",
        "--connect-timeout", "3.0", "-m", str(timeout), "-i", "-A", UA,
        "-x", proxy_url, url,
    ]
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buf = bytearray()
    header_end = -1
    first_body_t = None
    try:
        while len(buf) < max_bytes + 32768:
            chunk = proc.stdout.read(16384)
            if not chunk:
                break
            buf.extend(chunk)
            if header_end == -1:
                raw = bytes(buf)
                pos = 0
                while raw[pos : pos + 5].lower() == b"http/":
                    idx = raw.find(b"\r\n\r\n", pos)
                    if idx == -1:
                        break
                    pos = idx + 4
                if pos > 0 and raw[pos : pos + 5].lower() != b"http/" and len(raw) - pos >= 1:
                    header_end = pos
                    first_body_t = time.perf_counter()
            elif first_body_t is None and len(buf) > header_end:
                first_body_t = time.perf_counter()
            if header_end != -1 and (len(buf) - header_end) >= max_bytes:
                break
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=0.3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    t1 = time.perf_counter()
    elapsed = t1 - t0
    raw = bytes(buf)
    pos = 0
    blocks = []
    while raw[pos : pos + 5].lower() == b"http/":
        idx = raw.find(b"\r\n\r\n", pos)
        if idx == -1:
            break
        blocks.append(raw[pos:idx].decode("latin-1", errors="ignore"))
        pos = idx + 4
    body = raw[pos:]
    code = 0
    eff_url = url
    ctype = ""
    for blk in blocks:
        lines = blk.splitlines()
        if not lines:
            continue
        if "connection established" in lines[0].lower():
            continue
        m = re.match(r"HTTP/\S+\s+(\d+)", lines[0], re.I)
        c = int(m.group(1)) if m else 0
        if c == 100:
            continue
        code = c
        ctype = ""
        for h in lines[1:]:
            if ":" in h:
                k, v = h.split(":", 1)
                kl = k.strip().lower()
                if kl == "location" and c in (301, 302, 303, 307, 308):
                    eff_url = urllib.parse.urljoin(eff_url, v.strip())
                elif kl == "content-type":
                    ctype = v.strip().lower()
    body_elapsed = (t1 - first_body_t) if first_body_t is not None else elapsed
    return code, eff_url, ctype, body, elapsed, body_elapsed


def parse_hls_master_variants(text: str, base_url: str):
    """Return (variants, max_height, has_video, drm_detected)."""
    if re.search(r"#EXT-X-(KEY|SESSION-KEY):[^\n]*(SAMPLE-AES|widevine|skd://)", text, re.I):
        return [], 0, False, True

    variants = []
    max_height = 0
    saw_stream_inf = False
    has_video = False
    lines = text.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#EXT-X-STREAM-INF:"):
            saw_stream_inf = True
            attrs = s[len("#EXT-X-STREAM-INF:") :]
            res_m = re.search(r"RESOLUTION=(\d+)x(\d+)", attrs, re.I)
            bw_m = re.search(r"BANDWIDTH=(\d+)", attrs, re.I)
            cod_m = re.search(r'CODECS="([^"]*)"', attrs, re.I)
            h = int(res_m.group(2)) if res_m else 0
            bw = int(bw_m.group(1)) if bw_m else 0
            codecs = cod_m.group(1).lower() if cod_m else ""
            # Reject audio-only variants
            if codecs and not any(v in codecs for v in ("avc", "hvc", "hev", "h264", "h265", "vp8", "vp9", "av01", "mp4v")):
                continue
            has_video = True
            if h > max_height:
                max_height = h
            # Next non-comment line is URI
            for j in range(i + 1, len(lines)):
                nxt = lines[j].strip()
                if nxt and not nxt.startswith("#"):
                    variants.append((h, bw, urllib.parse.urljoin(base_url, nxt)))
                    break
    if saw_stream_inf:
        return variants, max_height, has_video, False
    return [], 0, True, False


def extract_first_media_segment(text: str, base_url: str) -> tuple[str | None, bool]:
    """Return (segment_url, is_audio_only)."""
    if re.search(r"#EXT-X-(KEY|SESSION-KEY):[^\n]*(SAMPLE-AES|widevine|skd://)", text, re.I):
        return None, True
    lines = text.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#EXTINF:"):
            for j in range(i + 1, len(lines)):
                nxt = lines[j].strip()
                if nxt and not nxt.startswith("#"):
                    seg = urllib.parse.urljoin(base_url, nxt)
                    path_low = urllib.parse.urlsplit(seg).path.lower()
                    if path_low.endswith((".aac", ".mp3", ".m4a", ".ac3", ".ec3")):
                        return None, True
                    return seg, False
    return None, False


def probe_url_on_route(url: str, route: str) -> dict | None:
    """Strictly probe playability, resolution (>=480p if declared), startup time, and segment throughput."""
    proxy = f"http://{ROUTER_IP}:{PROBE_PORTS[route]}"
    orig_host = strip_port(urllib.parse.urlsplit(url).netloc)
    code, eff_url, ctype, body, t_man, bt_man = fetch_http_prefix(url, proxy, timeout=4.5, max_bytes=204800)
    if code != 200 or not body:
        return None
    eff_host = strip_port(urllib.parse.urlsplit(eff_url).netloc)

    head_txt = body[:4096].decode("utf-8", errors="ignore")
    # Case 1: HLS Playlist
    if "#EXTM3U" in head_txt or "#EXT-X-" in head_txt:
        full_txt = body.decode("utf-8", errors="ignore")
        variants, max_h, has_vid, drm = parse_hls_master_variants(full_txt, eff_url)
        if drm or not has_vid:
            return None
        if variants and max_h > 0 and max_h < 480:
            return None

        media_url = eff_url
        media_txt = full_txt
        variant_host = eff_host
        t_var = 0.0
        if variants:
            # Prefer mid-to-high variant <= 1080p for realistic playback test
            eligible = [v for v in variants if v[0] == 0 or v[0] >= 480]
            if not eligible:
                return None
            eligible.sort(key=lambda x: (x[0] if x[0] <= 1080 else 720, x[1]))
            chosen = eligible[-1] if len(eligible) <= 2 else eligible[-2]
            c2, eu2, _, b2, t_var, _ = fetch_http_prefix(chosen[2], proxy, timeout=4.0, max_bytes=204800)
            if c2 != 200 or not b2:
                return None
            media_url = eu2
            variant_host = strip_port(urllib.parse.urlsplit(eu2).netloc)
            media_txt = b2.decode("utf-8", errors="ignore")
            if "#EXTM3U" not in media_txt[:200] and "#EXT-X-" not in media_txt[:200]:
                return None

        seg_url, audio_only = extract_first_media_segment(media_txt, media_url)
        if audio_only or not seg_url:
            return None

        c3, eu3, ct3, b3, t_seg, bt_seg = fetch_http_prefix(seg_url, proxy, timeout=3.5, max_bytes=196608)
        if c3 != 200 or len(b3) < 32768:
            return None
        if "text/html" in ct3 or b3.lstrip()[:5].lower() in (b"<html", b"<!doc"):
            return None
        seg_host = strip_port(urllib.parse.urlsplit(eu3).netloc)

        total_startup = t_man + t_var + t_seg
        speed_kbps = (len(b3) / 1024.0) / max(0.08, bt_seg)
        overall_seg_kbps = (len(b3) / 1024.0) / max(0.08, t_seg)
        if total_startup > 5.5 or speed_kbps < 150.0 or overall_seg_kbps < 60.0:
            return None

        hosts = {h for h in (orig_host, eff_host, variant_host, seg_host) if h and not is_ip_host(h)}
        ips = {h for h in (orig_host, eff_host, variant_host, seg_host) if h and is_ip_host(h)}
        return {
            "url": url,
            "route": route,
            "orig_host": orig_host,
            "eff_host": eff_host,
            "variant_host": variant_host,
            "seg_host": seg_host,
            "hosts": sorted(hosts),
            "ips": sorted(ips),
            "startup_sec": round(total_startup, 3),
            "speed_kbps": round(speed_kbps, 1),
            "max_height": max_h,
        }

    # Case 2: Continuous direct HTTP-TS / FLV stream
    if "text/html" in ctype or "application/json" in ctype or body.lstrip()[:1] in (b"<", b"{"):
        return None
    if len(body) < 32768:
        return None
    speed_kbps = (len(body) / 1024.0) / max(0.08, bt_man)
    if t_man > 5.5 or speed_kbps < 150.0:
        return None

    hosts = {h for h in (orig_host, eff_host) if h and not is_ip_host(h)}
    ips = {h for h in (orig_host, eff_host) if h and is_ip_host(h)}
    return {
        "url": url,
        "route": route,
        "orig_host": orig_host,
        "eff_host": eff_host,
        "variant_host": eff_host,
        "seg_host": eff_host,
        "hosts": sorted(hosts),
        "ips": sorted(ips),
        "startup_sec": round(t_man, 3),
        "speed_kbps": round(speed_kbps, 1),
        "max_height": 0,
    }


def route_plan_for_item(item: dict, cat: str, lang: str, active_routes: set[str]) -> list[str]:
    host = strip_port(urllib.parse.urlsplit(item["url"]).netloc)
    reg = item["region"]

    if cat in ("央视频道", "卫视频道", "中文数字/少儿/地方"):
        plan = ["direct"]
    elif cat == "港澳台":
        plan = ["direct", "tw", "hk"]
    elif cat == "新马华语":
        plan = ["direct", "sg", "tw"]
    elif lang == "jp" or cat == "日本频道":
        plan = ["direct", "jp", "tw"]
    elif lang == "kr" or cat == "韩国频道":
        if host == "jmp2.uk":
            plan = ["us"]
        elif reg in ("us", "uk", "ca"):
            plan = ["direct", "us", reg, "kr", "jp"]
        else:
            plan = ["direct", "kr", "jp", "us"]
    else:
        # English / FAST
        if host in ("jmp2.uk", "epg.provider.plex.tv"):
            plan = ["us"]
        elif reg == "uk":
            plan = ["direct", "us", "uk"]
        elif reg == "ca":
            plan = ["direct", "us", "ca"]
        else:
            plan = ["direct", "us"]

    return [r for r in plan if r in active_routes]


def probe_candidate(task: tuple) -> tuple[str, dict | None]:
    canonical, cat, lang, item, routes = task
    best = None
    for idx, r in enumerate(routes):
        res = probe_url_on_route(item["url"], r)
        if res:
            res["item"] = item
            # Early stop on fast direct so domestic/direct-capable streams avoid proxy hop
            if r == "direct" and res["startup_sec"] <= 2.2 and res["speed_kbps"] >= 200.0:
                return canonical, res
            if best is None:
                best = res
            else:
                # Prefer direct if reasonably fast, otherwise lower startup latency
                if best["route"] == "direct" and best["startup_sec"] <= 2.2:
                    pass
                elif res["startup_sec"] < best["startup_sec"] - 0.3:
                    best = res
            # Don't burn extra proxy probes once US or primary fallback already plays cleanly under 2.5s
            if best["startup_sec"] <= 2.5 and best["route"] in ("us", "tw", "jp"):
                break
    return canonical, best


def is_safety_excluded(host: str) -> bool:
    h = host.lower().strip(".")
    if h in SAFETY_EXCLUDED_DOMAINS:
        return True
    parts = h.split(".")
    if len(parts) <= 2 and h in SAFETY_EXCLUDED_DOMAINS:
        return True
    # Also exclude exact root domains like google.com etc.
    for root in SAFETY_EXCLUDED_DOMAINS:
        if h == root:
            return True
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Only run ingestion, filtering, and dedup stats without probing.")
    parser.add_argument("--workers", type=int, default=44, help="Concurrent probe threads.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    t_start = time.perf_counter()
    print("🚀 Step 1A-1C: 拉取并清洗融合 live.txt + 11 个 FAST 源 (仅保留中/英/日/韩高质频道)...")
    channels, stats = collect_candidates()
    print(
        f"📊 预筛选完成: 清洗后去重唯一频道 {stats['unique_channels_pre_probe']} 个，"
        f"待实测候选流 {stats['candidates_to_probe']} 条。"
    )
    print(f"   语种分布: {dict(stats['lang_counts'])}")
    print(f"   过滤统计: {dict(stats['dropped_reasons'])}")

    if args.dry_run:
        cat_cnt = Counter(ch["category"] for ch in channels.values())
        print("   目标分类预览:", dict(cat_cnt))
        return

    print("\n🔧 Step 1D: 在旁路由启动隔离的临时多地区探测 Mihomo 守护进程...")
    start_router_probe_daemon()
    try:
        working_countries = smoke_test_probe_ports()
        for req_route in ("direct", "us", "uk", "jp", "tw"):
            if req_route not in working_countries:
                raise RuntimeError(f"核心探测端口 {req_route} 未能通过出口国家校验: {working_countries}")
        active_routes = set(working_countries.keys())

        tasks = []
        for canonical, ch in channels.items():
            for it in ch["candidates"]:
                rlist = route_plan_for_item(it, ch["category"], ch["lang"], active_routes)
                if rlist:
                    tasks.append((canonical, ch["category"], ch["lang"], it, rlist))

        print(f"\n⚡ Step 1E: 启动 {args.workers} 线程实测 {len(tasks)} 条流 (M3U8+分辨率+首片视频测速)...")
        passed_by_channel: dict[str, list[dict]] = defaultdict(list)
        done = 0
        ok_cnt = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(probe_candidate, t) for t in tasks]
            for f in as_completed(futs):
                done += 1
                try:
                    canonical, res = f.result()
                    if res:
                        passed_by_channel[canonical].append(res)
                        ok_cnt += 1
                except Exception:
                    pass
                if done % 300 == 0 or done == len(tasks):
                    print(f"   进度: {done}/{len(tasks)} (已通过测速: {ok_cnt} 条, {time.perf_counter() - t_start:.1f}s)")
    finally:
        print("\n🧹 清理旁路由临时探测守护进程与临时文件...")
        stop_router_probe_daemon()

    # Step 1F: Resolve host -> single winning route + check route consistency
    host_route_votes: dict[str, Counter] = defaultdict(Counter)
    ip_route_votes: dict[str, Counter] = defaultdict(Counter)
    for canonical, results in passed_by_channel.items():
        # Count per-channel host votes so multi-URL channels don't skew excessively, and also weight direct > us if equal
        for res in results:
            r = res["route"]
            for h in res["hosts"]:
                if not is_safety_excluded(h):
                    host_route_votes[h][r] += 1
            for ip in res["ips"]:
                ip_route_votes[ip][r] += 1

    host_winner: dict[str, str] = {}
    for h, votes in host_route_votes.items():
        # Prefer direct if tied or >= 40% pass on direct; else highest vote count (preferring us on ties among proxy regions)
        best_r, best_v = votes.most_common(1)[0]
        if votes.get("direct", 0) > 0 and votes["direct"] * 2 >= best_v:
            best_r = "direct"
        elif "us" in votes and votes["us"] == best_v:
            best_r = "us"
        host_winner[h] = best_r

    ip_winner: dict[str, str] = {}
    for ip, votes in ip_route_votes.items():
        best_r, best_v = votes.most_common(1)[0]
        if votes.get("direct", 0) > 0:
            best_r = "direct"
        ip_winner[ip] = best_r

    # Consistency filter: keep only streams where ALL hosts align with the winning route it passed on
    final_by_cat: dict[str, list[tuple[str, list[dict]]]] = {c: [] for c in TARGET_CATEGORIES}
    route_conflict_dropped = 0
    total_output_streams = 0
    surviving_hosts_by_route: dict[str, set[str]] = defaultdict(set)
    surviving_ips_by_route: dict[str, set[str]] = defaultdict(set)

    for canonical, ch in channels.items():
        res_list = passed_by_channel.get(canonical, [])
        if not res_list:
            continue
        consistent = []
        for res in res_list:
            r = res["route"]
            conflict = False
            for h in res["hosts"]:
                if h in host_winner and host_winner[h] != r:
                    conflict = True
                    break
            for ip in res["ips"]:
                if ip in ip_winner and ip_winner[ip] != r:
                    conflict = True
                    break
            if conflict:
                route_conflict_dropped += 1
                continue
            consistent.append(res)

        if not consistent:
            continue

        # Sort: prefer direct when fast (<=2.0s), then lowest startup_sec, then highest speed_kbps
        consistent.sort(
            key=lambda x: (
                0 if (x["route"] == "direct" and x["startup_sec"] <= 2.0) else 1,
                x["startup_sec"],
                -x["speed_kbps"],
            )
        )
        cat = ch["category"]
        cap = 3 if cat in ("央视频道", "卫视频道", "港澳台") else 2
        kept = consistent[:cap]
        total_output_streams += len(kept)

        for res in kept:
            r = res["route"]
            for h in res["hosts"]:
                if not is_safety_excluded(h):
                    surviving_hosts_by_route[r].add(h)
            for ip in res["ips"]:
                surviving_ips_by_route[r].add(ip)

        final_by_cat[cat].append((ch["display"], kept))

    # Write live_plus.txt
    out_lines = []
    cat_summary = {}
    for cat in TARGET_CATEGORIES:
        entries = final_by_cat[cat]
        if not entries:
            continue
        out_lines.append(f"{cat},#genre#")
        stream_cnt = 0
        for disp, kept in entries:
            for res in kept:
                out_lines.append(f"{disp},{res['url']}")
                stream_cnt += 1
        cat_summary[cat] = {"channels": len(entries), "streams": stream_cnt}

    OUTPUT_LIVE_PLUS.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    # Write OpenClash rule-provider YAML bundle + summary report to scratch dir
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for route, hosts in surviving_hosts_by_route.items():
        if not hosts:
            continue
        payload = "---\npayload:\n" + "\n".join(f"- '{h}'" for h in sorted(hosts)) + "\n"
        (args.out_dir / f"tv_live_{route}_domain.yaml").write_text(payload, encoding="utf-8")

    for route, ips in surviving_ips_by_route.items():
        if route == "direct" or not ips:
            continue
        payload = "---\npayload:\n" + "\n".join(f"- '{ip}/32'" for ip in sorted(ips)) + "\n"
        (args.out_dir / f"tv_live_{route}_ip.yaml").write_text(payload, encoding="utf-8")

    report = {
        "elapsed_sec": round(time.perf_counter() - t_start, 1),
        "smoke_test_countries": working_countries,
        "pre_probe": stats["unique_channels_pre_probe"],
        "candidates_probed": stats["candidates_to_probe"],
        "route_conflict_dropped": route_conflict_dropped,
        "surviving_channels": sum(v["channels"] for v in cat_summary.values()),
        "surviving_streams": total_output_streams,
        "category_summary": cat_summary,
        "domains_by_route": {r: len(hs) for r, hs in surviving_hosts_by_route.items()},
        "ips_by_route": {r: len(ips) for r, ips in surviving_ips_by_route.items()},
        "raw_counts": stats["raw_counts"],
        "dropped_reasons": dict(stats["dropped_reasons"]),
    }
    (args.out_dir / "probe_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"\n🎉 完成! 耗时 {report['elapsed_sec']}s")
    print(f"💾 已生成精选直播源: {OUTPUT_LIVE_PLUS} ({report['surviving_channels']} 个独立频道, {report['surviving_streams']} 条验证存活流)")
    print("📁 分类汇总:")
    for cat, info in cat_summary.items():
        print(f"   {cat:16s}: {info['channels']:4d} 频道 / {info['streams']:4d} 条流")
    print("🌐 域名按最优路由分布:", report["domains_by_route"])
    print("🔢 IP 按路由分布:", report["ips_by_route"])
    print(f"📄 规则文件与详细报告已保存至: {args.out_dir}")


if __name__ == "__main__":
    main()
