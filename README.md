# 🎵 歌词批量下载器 (LRC Downloader)

一款 Windows 桌面工具：**一键扫描音乐文件夹（含所有子目录），批量搜索并下载与音乐同名的 `.lrc` 歌词文件**。

多平台接口自动切换 + 精确/模糊双重匹配 + 纯音乐智能识别，纯 Python 标准库实现，零第三方依赖。

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)
![Python](https://img.shields.io/badge/python-3.8%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## ✨ 功能特性

### 多接口搜索
按顺序自动尝试三个在线歌词源，一个失败自动切换下一个：

| 接口 | 说明 |
|---|---|
| 网易云音乐 | 搜索 + 歌词 API |
| 酷狗音乐 | 搜索 + KRC 歌词库（hash 查询 + 候选名二次校验） |
| QQ 音乐 | 搜索 + 歌词 API |

### 智能文件名解析
兼容各种常见命名方式，"歌名 - 歌手" 与 "歌手 - 歌名" 两种顺序都能正确解析：

```
最远的你是我最近的爱 - 小曼.mp3   →  最远的你是我最近的爱 - 小曼.lrc
缘分一道桥 - 王力宏／谭维维.mp3   →  缘分一道桥 - 王力宏／谭维维.lrc
杨青 - 半山听雨.ape              →  杨青 - 半山听雨.lrc
```

### 精确 + 模糊双重匹配
- 优先精确匹配歌名，相似度 1.0 直接采用
- 搜不到时启用模糊匹配（阈值 0.55），并自动跳过返回垃圾数据的候选、尝试下一个最佳匹配
- 可调阈值（`download_lrc.py` 中 `FUZZY_THRESHOLD`）

### 纯音乐智能识别 ⭐
纯音乐没有歌词是正常的，本工具**宁缺毋滥**：
- 自动识别 AI 哼唱字幕（"嗯嗯嗯嗯the嗯" 这类无意义内容）
- 自动识别平台占位提示（"此歌曲为没有填词的纯音乐，请您欣赏"）
- 判定为纯音乐时不生成 `.lrc`，并自动清理此前误存的占位歌词

### 多格式支持
`mp3` `flac` `wav` `ape` `ogg` `m4a` `wma` `aac` `opus` `wv` `dsf`

---

## 📦 下载安装

### 方式一：直接使用（推荐，无需 Python）
前往 [**Releases**](../../releases) 页面下载 `LRC-Downloader-v1.0.0-Windows-x64.zip`，解压后双击 `歌词批量下载器.exe` 即可。

> 单文件免安装，内置 Python 运行时，可复制到任何 Windows 10/11 64 位电脑使用。
> 首次启动需 2~3 秒解压加载，属正常现象。

### 方式二：从源码运行（需 Python 3.8+）
```bash
git clone https://github.com/<你的用户名>/lrc-downloader.git
cd lrc-downloader
python lrc_gui.py          # 图形界面
python download_lrc.py D:\音乐 -r   # 命令行递归模式
```

---

## 🖥️ 界面功能

| 功能 | 说明 |
|---|---|
| 文件夹选择 | 选择后立即显示音乐文件数量 |
| 包含所有子文件夹 | 递归扫描全部层级，歌词保存到音乐文件各自所在目录 |
| 覆盖已存在的歌词 | 默认跳过已有 `.lrc`，勾选后强制重新下载 |
| 实时日志 | 每首歌的歌词完整路径、模糊匹配过程彩色显示 |
| 目录级汇总 | 每个文件夹处理完立即输出 "成功/纯音乐/跳过/失败" 统计 |
| 总体汇总 | 全部完成后弹窗提示总结果 |
| 进度条 + 停止 | 实时进度，随时安全中断 |

---

## 🚀 自行打包 exe

```bash
pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed ^
    --name "歌词批量下载器" --icon app.ico lrc_gui.py
```

---

## 📁 项目结构

```
├── lrc_gui.py                  # Windows 图形界面（tkinter，零依赖）
├── download_lrc.py             # 下载核心（多接口 + 匹配逻辑 + CLI）
├── 启动歌词下载器.bat           # Windows 双击启动脚本
├── app.ico                     # 应用图标
└── Releases: LRC-Downloader-v1.0.0-Windows-x64.zip   # 免安装发行包
```

## 🛠️ 技术说明

- **零第三方依赖**：界面用 tkinter，网络请求用 urllib，模糊匹配用 difflib
- **酷狗 KRC 修复**：按 hash 查歌词时常返回无关候选（如 June-Barcarole 垃圾数据），通过候选歌名/歌手与目标的相似度二次校验解决
- **线程模型**：GUI 下载在后台线程运行，通过消息队列 + 定时轮询刷新界面，全程不卡 UI

## ⚠️ 免责声明

本项目仅供学习交流使用，歌词内容版权归各平台及版权方所有，请勿用于商业用途。

## 📄 License

[MIT](LICENSE)
