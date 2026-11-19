#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TVBox / 影视仓 / OK影视 自动化采集源测活、测速与智能备用降级脚本
特性：
1. 采用【多节点智能降级】机制：每个主流资源站配置多组活跃镜像与 http/https 双协议候选；
2. 并发探测：解决国内采集站 SSL 握手超时、主域被墙与频繁换域问题；
3. 严格校验：HTTP 200 + 有效 JSON + 非空视频列表；
4. 延迟升序排序：确保电视端始终优先从当前响应最快的节点拉取。
"""

import json
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ==================== 配置常量 ====================
ENDPOINT_TIMEOUT_SEC = 2.8   # 单个节点探测超时（秒）
MAX_WORKERS = 12            # 并发检测站点数
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = REPO_ROOT / "vod.json"

# 通用分类过滤（纯净精选常规分类）
STANDARD_CATEGORIES = [
    "动作片", "喜剧片", "爱情片", "科幻片", "恐怖片", "剧情片", "战争片", "纪录片",
    "国产剧", "欧美剧", "香港剧", "韩国剧", "台湾剧", "日本剧", "海外剧", "泰国剧",
    "大陆综艺", "港台综艺", "日韩综艺", "欧美综艺", "国产动漫", "日韩动漫", "欧美动漫"
]

# ==================== 候选切片源池 (每个主流源均配置官方主备镜像与协议回退) ====================
CANDIDATE_SITES = [
    {
        "key": "360zy",
        "name": "360秒播",
        "endpoints": [
            "http://360zyzz.com/api.php/provide/vod/",
            "https://360zyzz.com/api.php/provide/vod/",
            "https://360zy.com/api.php/provide/vod/"
        ]
    },
    {
        "key": "ffzy",
        "name": "非凡秒播",
        "endpoints": [
            "http://ffzy5.tv/api.php/provide/vod/from/ffm3u8/",
            "http://cj.ffzyapi.com/api.php/provide/vod/from/ffm3u8/",
            "https://ffzy5.tv/api.php/provide/vod/from/ffm3u8/",
            "https://ffzy5.tv/api.php/provide/vod/"
        ]
    },
    {
        "key": "hnzy",
        "name": "红牛秒播",
        "endpoints": [
            "https://www.hongniuzy2.com/api.php/provide/vod/from/hnm3u8/",
            "https://www.hongniuzy3.com/api.php/provide/vod/from/hnm3u8/",
            "http://www.hongniuzy2.com/api.php/provide/vod/from/hnm3u8/"
        ]
    },
    {
        "key": "bfzy",
        "name": "暴风秒播",
        "endpoints": [
            "http://bfzy1.tv/api.php/provide/vod/",
            "http://bfzy2.tv/api.php/provide/vod/",
            "http://bfzy5.tv/api.php/provide/vod/",
            "https://bfzyapi.com/api.php/provide/vod/"
        ]
    },
    {
        "key": "lzi",
        "name": "量子秒播",
        "endpoints": [
            "http://cj.lziapi.com/api.php/provide/vod/from/lzm3u8/",
            "http://cj.lziapi.com/api.php/provide/vod/",
            "https://cj.lziapi.com/api.php/provide/vod/from/lzm3u8/"
        ]
    },
    {
        "key": "sdzy",
        "name": "闪电秒播",
        "endpoints": [
            "http://sdzyapi.com/api.php/provide/vod/",
            "http://xsd.sdzyapi.com/api.php/provide/vod/",
            "https://sdzyapi.com/api.php/provide/vod/"
        ]
    },
    {
        "key": "huya",
        "name": "虎牙秒播",
        "endpoints": [
            "https://www.huyaapi.com/api.php/provide/vod/from/hym3u8/",
            "http://www.huyaapi.com/api.php/provide/vod/from/hym3u8/"
        ]
    },
    {
        "key": "hhzy",
        "name": "火狐秒播",
        "endpoints": [
            "https://hhzyapi.com/api.php/provide/vod/from/hhm3u8/",
            "http://hhzyapi.com/api.php/provide/vod/from/hhm3u8/"
        ]
    },
    {
        "key": "bdzy",
        "name": "百度秒播",
        "endpoints": [
            "http://api.apibdzy.com/api.php/provide/vod/",
            "https://api.apibdzy.com/api.php/provide/vod/"
        ]
    },
    {
        "key": "tpzy",
        "name": "淘片秒播",
        "endpoints": [
            "https://taopianapi.com/cjapi/mc10/vod/json.html",
            "http://taopianapi.com/cjapi/mc10/vod/json.html"
        ]
    },
    {
        "key": "snzy",
        "name": "索尼秒播",
        "endpoints": [
            "https://suoniapi.com/api.php/provide/vod/",
            "http://suoniapi.com/api.php/provide/vod/"
        ]
    },
    {
        "key": "gszy",
        "name": "光速秒播",
        "endpoints": [
            "https://api.guangsuapi.com/api.php/provide/vod/from/gsm3u8/",
            "http://api.guangsuapi.com/api.php/provide/vod/from/gsm3u8/"
        ]
    },
    {
        "key": "jszy",
        "name": "极速秒播",
        "endpoints": [
            "https://jszyapi.com/api.php/provide/vod/from/jsm3u8/",
            "http://jszyapi.com/api.php/provide/vod/from/jsm3u8/"
        ]
    },
    {
        "key": "jyzy",
        "name": "金鹰秒播",
        "endpoints": [
            "https://jyzyapi.com/provide/vod/",
            "http://jyzyapi.com/provide/vod/",
            "https://jyzyapi.com/api.php/provide/vod/"
        ]
    },
    {
        "key": "mtzy",
        "name": "茅台秒播",
        "endpoints": [
            "https://caiji.maotaizy.cc/api.php/provide/vod/from/mtm3u8/",
            "http://caiji.maotaizy.cc/api.php/provide/vod/from/mtm3u8/"
        ]
    },
    {
        "key": "wjzy",
        "name": "无尽秒播",
        "endpoints": [
            "https://api.wujinapi.net/api.php/provide/vod/",
            "https://api.wujinapi.me/api.php/provide/vod/"
        ]
    },
    {
        "key": "subo",
        "name": "速播秒播",
        "endpoints": [
            "http://subocaiji.com/api.php/provide/vod/from/subm3u8/",
            "https://subocaiji.com/api.php/provide/vod/from/subm3u8/"
        ]
    },
    {
        "key": "kczy",
        "name": "快车秒播",
        "endpoints": [
            "http://caiji.kuaichezy.org/api.php/provide/vod/",
            "https://caiji.kuaichezy.org/api.php/provide/vod/"
        ]
    },
    {
        "key": "xlzy",
        "name": "新浪秒播",
        "endpoints": [
            "http://api.xinlangapi.com/xinlangapi.php/provide/vod/from/xlm3u8/",
            "https://api.xinlangapi.com/xinlangapi.php/provide/vod/from/xlm3u8/"
        ]
    },
    {
        "key": "ukzy",
        "name": "U酷秒播",
        "endpoints": [
            "https://api.ukuapi88.com/api.php/provide/vod/from/ukm3u8/",
            "https://api.ukuapi.com/api.php/provide/vod/"
        ]
    },
    {
        "key": "yyzy",
        "name": "优质秒播",
        "endpoints": [
            "https://api.yyzy-tv.vip/inc/apijson.php",
            "http://api.yyzy-tv.vip/inc/apijson.php"
        ]
    }
]

# 经典 m3u8 切片广告去重/过滤规则
DEFAULT_RULES = [
    {
        "name": "量子",
        "hosts": ["lzcdn", "lz-cdn", "cdnlz", "lziplayer"],
        "regex": ["#EXT-X-DISCONTINUITY\\r?\\n(?:#EXTINF:[\\d.]+,\\r?\\n/\\d{8}/[^\\r\\n]*/\\d+k/hls/[^\\r\\n]*\\r?\\n)+"]
    },
    {
        "name": "暴风",
        "hosts": ["bfllvip", "rrcdnbf", "bfvvs"],
        "regex": ["#EXT-X-DISCONTINUITY\\r?\\n(?:#EXTINF:[\\d.]+,\\r?\\n[^\\r\\n]*adjump[^\\r\\n]*\\r?\\n)+"]
    },
    {
        "name": "360/猫眼/电影天堂",
        "hosts": ["360zyx", "maowushi", "maoyanplay", "dytt-"],
        "regex": [
            "#EXT-X-DISCONTINUITY\\r?\\n#EXT-X-KEY:METHOD=NONE\\r?\\n(?:#EXTINF:[\\d.]+,\\r?\\n[^\\r\\n#]+\\r?\\n){1,6}(?=#EXT-X-DISCONTINUITY|#EXT-X-ENDLIST)",
            "#EXT-X-DISCONTINUITY\\r?\\n(?:#EXTINF:[\\d.]+,\\r?\\n[^\\r\\n#]+\\r?\\n){1,5}(?=#EXT-X-DISCONTINUITY|#EXT-X-ENDLIST)"
        ]
    },
    {
        "name": "非凡",
        "hosts": ["ffzy", "feifei-online"],
        "regex": [
            "#EXT-X-DISCONTINUITY\\r?\\n#EXTINF:6\\.666667,[\\s\\S]*?#EXT-X-DISCONTINUITY",
            "#EXTINF.*?\\s+.*?1171(057)?.*?\\.ts"
        ]
    }
]


def check_site(site: dict) -> dict | None:
    """
    对单个站点进行多节点探测。
    只要候选节点中有一个通过健康检验，即认为该站点存活，并采用该节点。
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }

    for ep in site["endpoints"]:
        sep = "&" if "?" in ep else "?"
        test_url = f"{ep}{sep}ac=detail&pagesize=1"
        req = urllib.request.Request(test_url, headers=headers, method="GET")
        start_time = time.perf_counter()

        try:
            with urllib.request.urlopen(req, timeout=ENDPOINT_TIMEOUT_SEC, context=ctx) as response:
                if response.status != 200:
                    continue

                raw_body = response.read().decode("utf-8", errors="ignore")
                latency_ms = int((time.perf_counter() - start_time) * 1000)

                data = json.loads(raw_body)
                if isinstance(data, dict) and "list" in data and isinstance(data["list"], list) and len(data["list"]) > 0:
                    print(f"✅ [{site['name']}] 命中可用节点: {ep} ({latency_ms}ms)")
                    return {
                        "key": site["key"],
                        "name": site["name"],
                        "api": ep,
                        "latency": latency_ms
                    }
        except Exception:
            continue

    print(f"💀 [{site['name']}] 所有候选节点均连接失败或超时")
    return None


def build_config(valid_results: list) -> dict:
    """按延迟排序并组装成 TVBox vod.json 规范配置"""
    sites_list = []
    for idx, item in enumerate(valid_results, 1):
        latency = item["latency"]
        tag = "🚀" if idx <= 3 else "⚡"
        display_name = f"{tag} {item['name']} [{latency}ms]"

        sites_list.append({
            "key": f"tim_{item['key']}",
            "name": display_name,
            "type": 1,  # 1: 苹果CMS MacCMS v10 JSON API
            "api": item["api"],
            "searchable": 1,
            "quickSearch": 1,
            "changeable": 1,
            "playerType": 2,  # ExoPlayer / IJK 硬解秒播
            "categories": STANDARD_CATEGORIES
        })

    return {
        "wallpaper": "https://tuapi.eees.cc/api.php?category=fengjing&type=302",
        "sites": sites_list,
        "rules": DEFAULT_RULES,
        "parses": [
            {"name": "Json并发", "type": 2, "url": "Parallel"},
            {"name": "Json轮询", "type": 2, "url": "Sequence"},
            {"name": "虾米解析", "type": 0, "url": "https://jx.xmflv.com/?url="}
        ],
        "flags": ["youku", "qq", "iqiyi", "qiyi", "letv", "sohu", "tudou", "pptv", "mgtv", "wasu", "bilibili"],
        "ads": ["mimg.0c1q0l.cn", "www.googletagmanager.com", "www.google-analytics.com", "mc.usihnbcq.cn"]
    }


def main():
    print(f"🚀 开始并发测活 {len(CANDIDATE_SITES)} 个主流秒播站点 (含主备镜像降级)...")
    valid_results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_site = {executor.submit(check_site, site): site for site in CANDIDATE_SITES}
        for future in as_completed(future_to_site):
            res = future.result()
            if res is not None:
                valid_results.append(res)

    if not valid_results:
        print("🚨 警告：所有站点均未通过测活！放弃本次覆写，保留原有配置。")
        exit(1)

    # 按延迟升序排序
    valid_results.sort(key=lambda x: x["latency"])
    print(f"\n📊 测活完成：存活 {len(valid_results)}/{len(CANDIDATE_SITES)} 个站点。最快源：{valid_results[0]['name']} ({valid_results[0]['latency']}ms)")

    config = build_config(valid_results)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"💾 成功写入最新配置文件: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
