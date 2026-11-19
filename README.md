# 📺 个人电视与影视聚合配置 (TV & VOD Config)

本仓库提供纯净切片点播源与全套电视台直播源，严格区分 **平台适配（iOS / Android / TV）** 与 **内容属性（纯净常规 / 成人 18+ / 全量综合）**。

- **GitHub 仓库**：[Trimmy7/tv-config](https://github.com/Trimmy7/tv-config)
- **底层特性**：
  - 核心采用标准苹果 CMS（MacCMS v10 JSON API，Type: 1），无 Java `.jar` 依赖，无网盘扫码限制，全平台秒播。
  - **⚡ GitHub Actions 自动化运维**：每日北京时间凌晨 04:00 并发测活 25+ 候选采集源，自动熔断死链，按响应延迟排序更新 `vod.json`。

---

## 🌟 推荐首选：多仓聚合入口（TVBox / OK 影视 / 影视仓）

在电视端只填入这一个多仓链接，即可同时拥有 **自建自动化秒播源 + 肥猫 + 饭太硬 + 摸鱼儿**，随时自由切换：

| 入口类型 | 🚀 国内高速镜像直链（推荐填入电视） | 🌐 GitHub 原始直连直链 |
| :--- | :--- | :--- |
| **全网多仓聚合入口** (`warehouse.json`) | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/warehouse.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/warehouse.json` |

*(备用 jsDelivr 直链：`https://cdn.jsdelivr.net/gh/Trimmy7/tv-config@main/warehouse.json`)*

---

## 一、 快速选型与单仓订阅地址矩阵

### 1. 📺 通用标准版点播（TVBox / 影视仓 / OK 影视 / TVS）

| 版本类型 | 内容包含 | 🚀 国内高速镜像直链（推荐） | 🌐 GitHub 原始直连直链 |
| :--- | :--- | :--- | :--- |
| **纯净秒播常规版** (`vod.json`) | 每日自动测活优选（前排秒播，无成人） | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod.json` |
| **🔞 成人专版** (`vod-18.json`) | 15 个成人专属源 | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod-18.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod-18.json` |
| **全量综合版** (`vod-all.json`) | 34 个常规 + 成人全部聚合源 | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod-all.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod-all.json` |

---

### 2. 📱 iOS 专版点播（uz 影视专用格式）

| 版本类型 | 内容包含 | 🚀 国内高速镜像直链（推荐） | 🌐 GitHub 原始直连直链 |
| :--- | :--- | :--- | :--- |
| **纯净常规版** | 19 个常规精选切片源（无成人） | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-vod.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-vod.json` |
| **🔞 成人专版** | 15 个成人专属源（带防误触上锁） | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-18.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-18.json` |
| **全量综合版** | 34 个常规 + 成人全部聚合源 | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-all.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-all.json` |

---

### 3. 📡 电视直播源（全平台通用 M3U / TXT）

| 版本类型 | 内容包含 | 🚀 国内高速镜像直链（推荐） | 🌐 GitHub 原始直连直链 |
| :--- | :--- | :--- | :--- |
| **纯净常规版** | 4700+ 央视、卫视、地方、港澳台、国际频道（无成人台） | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/live.txt` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/live.txt` |
| **🔞 成人专版** | 专属成人直播频道 | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/live-18.txt` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/live-18.txt` |
| **全量综合版** | 4800+ 频道（常规频道 + 成人频道全量） | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/live-all.txt` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/live-all.txt` |

---

## 二、 导入方法说明

### 1. TVBox / 影视仓 / OK 影视 / TVS
1. 复制上方 **多仓聚合入口**（或单仓版）镜像直链；
2. 打开软件 ➔ **【设置】** ➔ **【配置地址】/【订阅】** ➔ 粘贴链接保存即可；
3. 多仓切换：在软件首页或设置中点击“数据源 / 仓库”，即可在自建秒播、肥猫、饭太硬之间一键切换。

### 2. uz 影视 (iOS)
1. 复制上方对应的 uz 专版直链；
2. 打开 **uz 影视** ➔ 底栏 **【设置】** ➔ **【数据管理】** ➔ 点击 **【视频源】**；
3. 点击右上角 **`+` 号** ➔ 粘贴该链接 ➔ 确定。
