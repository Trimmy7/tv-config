# 📺 个人电视与影视聚合配置 (TV & VOD Config)

本仓库提供纯净切片点播源与全套电视台直播源，严格区分 **平台适配（iOS / Android / TV）** 与 **内容属性（纯净常规 / 成人 18+ / 全量综合）**。

- **GitHub 仓库**：[Trimmy7/tv-config](https://github.com/Trimmy7/tv-config)
- **底层特性**：全部采用标准苹果 CMS（MacCMS v10 JSON API，Type: 1），无 Java `.jar` 依赖，无网盘登录扫码限制，全平台秒播。

---

## 一、 快速选型与订阅地址矩阵

### 1. 📱 iOS 专版（uz 影视专用格式）

| 版本类型 | 内容包含 | 🚀 国内高速镜像直链（推荐） | 🌐 GitHub 原始直连直链 |
| :--- | :--- | :--- | :--- |
| **纯净常规版** | 19 个常规精选切片源（无成人） | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-vod.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-vod.json` |
| **成人专版 (18+)** | 15 个成人专属源（带防误触上锁） | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-18.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-18.json` |
| **全量综合版** | 34 个常规 + 成人全部聚合源 | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-all.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/uz-all.json` |

---

### 2. 📺 通用标准版（TVBox / 影视仓 / OK 影视 / TVS）

| 版本类型 | 内容包含 | 🚀 国内高速镜像直链（推荐） | 🌐 GitHub 原始直连直链 |
| :--- | :--- | :--- | :--- |
| **纯净常规版** | 19 个常规精选切片源（无成人） | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod.json` |
| **成人专版 (18+)** | 15 个成人专属源 | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod-18.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod-18.json` |
| **全量综合版** | 34 个常规 + 成人全部聚合源 | `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod-all.json` | `https://raw.githubusercontent.com/Trimmy7/tv-config/main/vod-all.json` |

---

### 3. 📡 全套电视直播源（全平台通用 M3U / TXT）

包含央视、卫视、各类 4K 超清与经典轮播频道：
- **🚀 国内高速镜像**：
  `https://ghfast.top/https://raw.githubusercontent.com/Trimmy7/tv-config/main/live.txt`
- **🌐 GitHub 原始直连**：
  `https://raw.githubusercontent.com/Trimmy7/tv-config/main/live.txt`

---

## 二、 导入方法说明

### 1. uz 影视 (iOS)
1. 复制上方对应的 uz 专版直链；
2. 打开 **uz 影视** ➔ 底栏 **【设置】** ➔ **【数据管理】** ➔ 点击 **【视频源】**；
3. 点击右上角 **`+` 号** ➔ 粘贴该链接 ➔ 确定；
4. 直播源同理：进入 **【数据管理】** ➔ **【直播源】** ➔ 点击右上角 `+` 号粘贴直播源链接即可。

### 2. TVBox / 影视仓 / OK 影视 / TVS
1. 复制上方对应的通用版直链；
2. 打开软件 ➔ **【设置】** ➔ **【配置地址】/【订阅】** ➔ 粘贴链接保存即可。
