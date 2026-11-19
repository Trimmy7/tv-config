#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TVBox / 影视仓 / OK影视 自动化采集源测活、测速与优选脚本
功能：
1. 并发探测苹果 CMS (MacCMS v10) 切片采集站可用性与网络延迟；
2. 过滤超时、失效、报错的死链；
3. 按照响应延迟升序排序（最快最稳的源排在最前）；
4. 保留防断流与 m3u8 切片跳过广告规则，组装成标准 TVBox vod.json 配置文件。
"""

import json
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ==================== 配置常量 ====================
TIMEOUT_SEC = 3.0   # 单个接口探测超时（秒）
MAX_WORKERS = 15   # 并发检测线程数
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = REPO_ROOT / "vod.json"

# 通用分类过滤（纯净精选常规分类）
STANDARD_CATEGORIES = [
    "动作片", "喜剧片", "爱情片", "科幻片", "恐怖片", "剧情片", "战争片", "纪录片",
    "国产剧", "欧美剧", "香港剧", "韩国剧", "台湾剧", "日本剧", "海外剧", "泰国剧",
    "大陆综艺", "港台综艺", "日韩综艺", "欧美综艺", "国产动漫", "日韩动漫", "欧美动漫"
]

# ==================== 候选切片源池 (25+ 主流优质采集站) ====================
CANDIDATE_SITES = [
    {"key": "snzy", "name": "索尼秒播", "api": "https://suoniapi.com/api.php/provide/vod/"},
    {"key": "hnzy", "name": "红牛秒播", "api": "https://www.hongniuzy2.com/api.php/provide/vod/from/hnm3u8/"},
    {"key": "hnzy_bak", "name": "红牛(备)", "api": "https://www.hongniuzy3.com/api.php/provide/vod/from/hnm3u8/"},
    {"key": "jszy", "name": "极速秒播", "api": "https://jszyapi.com/api.php/provide/vod/from/jsm3u8/"},
    {"key": "bdzy", "name": "百度秒播", "api": "https://api.apibdzy.com/api.php/provide/vod/"},
    {"key": "jyzy", "name": "金鹰秒播", "api": "https://jyzyapi.com/provide/vod/"},
    {"key": "mdzy", "name": "魔都秒播", "api": "https://www.mdzyapi.com/api.php/provide/vod/"},
    {"key": "subo", "name": "速播秒播", "api": "https://subocaiji.com/api.php/provide/vod/from/subm3u8/"},
    {"key": "huya", "name": "虎牙秒播", "api": "https://www.huyaapi.com/api.php/provide/vod/from/hym3u8/"},
    {"key": "gszy", "name": "光速秒播", "api": "https://api.guangsuapi.com/api.php/provide/vod/from/gsm3u8/"},
    {"key": "hhzy", "name": "火狐秒播", "api": "https://hhzyapi.com/api.php/provide/vod/from/hhm3u8/"},
    {"key": "mtzy", "name": "茅台秒播", "api": "https://caiji.maotaizy.cc/api.php/provide/vod/from/mtm3u8/"},
    {"key": "bfzy", "name": "暴风秒播", "api": "https://bfzyapi.com/api.php/provide/vod/"},
    {"key": "dytt", "name": "电影天堂", "api": "http://caiji.dyttzyapi.com/api.php/provide/vod/from/dyttm3u8/"},
    {"key": "lzi", "name": "量子秒播", "api": "https://cj.lziapi.com/api.php/provide/vod/from/lzm3u8/"},
    {"key": "lzi_bak", "name": "量子(备)", "api": "https://cj.lzzyapi.com/api.php/provide/vod/"},
    {"key": "ffzy", "name": "非凡秒播", "api": "https://cj.ffzyapi.com/api.php/provide/vod/from/ffm3u8/"},
    {"key": "ffzy_bak", "name": "非凡(备)", "api": "https://ffzy5.tv/api.php/provide/vod/"},
    {"key": "xlzy", "name": "新浪秒播", "api": "https://api.xinlangapi.com/xinlangapi.php/provide/vod/from/xlm3u8/"},
    {"key": "kczy", "name": "快车秒播", "api": "https://caiji.kuaichezy.org/api.php/provide/vod/"},
    {"key": "sdzy", "name": "闪电秒播", "api": "https://xsd.sdzyapi.com/api.php/provide/vod/"},
    {"key": "tpzy", "name": "淘片秒播", "api": "https://taopianapi.com/cjapi/mc10/vod/json.html"},
    {"key": "wjzy", "name": "无尽秒播", "api": "https://api.wujinapi.me/api.php/provide/vod/"},
    {"key": "ukzy", "name": "U酷秒播", "api": "https://api.ukuapi.com/api.php/provide/vod/"}
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
    """探测单个采集站的连通性、响应延迟及数据有效性"""
    api_url = site["api"]
    sep = "&" if "?" in api_url else "?"
    test_url = f"{api_url}{sep}ac=detail&pagesize=1"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }

    req = urllib.request.Request(test_url, headers=headers, method="GET")
    start_time = time.perf_counter()

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC, context=ctx) as response:
            if response.status != 200:
                print(f"❌ [{site['name']}] HTTP 状态码异常: {response.status}")
                return None

            raw_body = response.read().decode("utf-8", errors="ignore")
            latency_ms = int((time.perf_counter() - start_time) * 1000)

            data = json.loads(raw_body)
            # 严格校验返回数据结构：必须包含非空的 list
            if not isinstance(data, dict) or "list" not in data or not isinstance(data["list"], list) or len(data["list"]) == 0:
                print(f"❌ [{site['name']}] 返回数据结构无效或视频列表为空")
                return None

            print(f"✅ [{site['name']}] 测活通过 | 响应: {latency_ms}ms")
            return {
                "site": site,
                "latency": latency_ms
            }

    except urllib.error.URLError as e:
        print(f"💀 [{site['name']}] 连接失败: {e.reason}")
    except json.JSONDecodeError:
        print(f"💀 [{site['name']}] 返回非合法 JSON")
    except Exception as e:
        print(f"💀 [{site['name']}] 异常: {str(e)}")

    return None


def build_config(valid_results: list) -> dict:
    """按延迟排序并组装成 TVBox vod.json 规范配置"""
    sites_list = []
    for idx, item in enumerate(valid_results, 1):
        raw_site = item["site"]
        latency = item["latency"]

        # 前 3 名标火箭，其余标闪电
        tag = "🚀" if idx <= 3 else "⚡"
        display_name = f"{tag} {raw_site['name']} [{latency}ms]"

        sites_list.append({
            "key": f"tim_{raw_site['key']}",
            "name": display_name,
            "type": 1,  # 1: 苹果CMS MacCMS v10 JSON API
            "api": raw_site["api"],
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
    print(f"🚀 开始并发测活 {len(CANDIDATE_SITES)} 个切片源 (超时阈值: {TIMEOUT_SEC}s)...")
    valid_results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_site = {executor.submit(check_site, site): site for site in CANDIDATE_SITES}
        for future in as_completed(future_to_site):
            res = future.result()
            if res is not None:
                valid_results.append(res)

    # 防御性回退：若全部探测失败（例如网络异常），不覆写旧文件
    if not valid_results:
        print("🚨 警告：所有源均未通过测活！放弃本次覆写，保留原有配置。")
        exit(1)

    # 按延迟由低到高升序排序
    valid_results.sort(key=lambda x: x["latency"])
    print(f"\n📊 测活完成：存活 {len(valid_results)}/{len(CANDIDATE_SITES)} 个源。最快源：{valid_results[0]['site']['name']} ({valid_results[0]['latency']}ms)")

    config = build_config(valid_results)

    # 写入 vod.json
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"💾 成功写入最新配置文件: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
