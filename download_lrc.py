#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量下载歌词（.lrc）脚本
========================
扫描目录下的音乐文件（mp3 / flac / wav / ape / ogg / m4a / wma / aac /
opus / wv / dsf 等常见格式），自动从多个在线接口搜索并下载对应的 .lrc
歌词，保存为与音乐文件**完全同名**的歌词文件。

用法:
    python download_lrc.py            # 处理当前目录
    python download_lrc.py D:\\音乐   # 处理指定目录
    python download_lrc.py 歌曲.flac  # 处理单个音乐文件

特性:
  1. 多接口依次尝试: 网易云音乐 -> 酷狗 -> QQ音乐
  2. 先精确匹配，搜不到再用相似度模糊匹配（阈值 0.55，越高越严格）
  3. 文件名 "歌名 - 歌手" 与 "歌手 - 歌名" 两种顺序都会尝试
  4. 歌词文件名始终与音乐文件名保持一致（仅扩展名不同）
  5. 已存在同名 .lrc 时默认跳过（--force 可强制覆盖）
  6. 纯音乐自动识别：只有哼唱/AI 字幕时不会生成无意义的歌词文件
"""

import argparse
import base64
import difflib
import json
import os
import re
import sys
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- 基础工具

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
}

MUSIC_EXTS = {".mp3", ".flac", ".wav", ".ape", ".ogg", ".m4a", ".wma", ".aac", ".opus", ".wv", ".dsf"}

# 模糊匹配阈值：低于此分数视为不匹配
FUZZY_THRESHOLD = 0.55


def http_get(url, timeout=10, extra_headers=None):
    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_get_json(url, timeout=10, extra_headers=None):
    raw = http_get(url, timeout, extra_headers)
    return json.loads(raw.decode("utf-8", errors="ignore"))


def normalize(s):
    """归一化字符串用于比较：去空格/标点/全半角差异，转小写"""
    if not s:
        return ""
    s = s.lower()
    s = s.replace("／", "/").replace("、", " ")
    s = re.sub(r"[\s\-_·・,.，。：:;；！!？?（）()\[\]【】《》“”\"'‘’/\\|&]+", "", s)
    return s


def similarity(a, b):
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


# ---------------------------------------------------------------- 文件名解析

def parse_name(filename_no_ext):
    """
    从文件名解析出搜索用的关键词组合。
    兼容 "歌名 - 歌手" 和 "歌手 - 歌名" 两种顺序。
    返回按优先级排列的搜索词列表（可能含多个变体）。
    """
    name = filename_no_ext.strip()
    name = re.sub(r"\s*[\[(【（].*?[\])】）]\s*", " ", name)  # 去掉 (Live)/[HQ] 之类的标注
    name = re.sub(r"\s+", " ", name).strip()

    # 常见分隔符: " - " / "-" / "_" / "–"
    parts = None
    for sep in [" - ", " – ", " -", "- ", "_"]:
        if sep in name:
            two = [p.strip() for p in name.split(sep, 1)]
            if len(two) == 2 and two[0] and two[1]:
                parts = two
                break
    if parts is None and len(name.split("-")) >= 2:
        seg = [p.strip() for p in name.split("-", 1)]
        if all(seg):
            parts = seg

    keys = []
    if parts:
        a, b = parts
        keys.append(f"{a} {b}")   # 原顺序整体搜索
        keys.append(f"{b} {a}")   # 反序（处理 "歌手 - 歌名"）
        keys.append(a)            # 只用第一段
        keys.append(b)            # 只用第二段
    else:
        keys.append(name)
    # 去重保序
    seen, out = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


# ---------------------------------------------------------------- 各接口实现
# 每个搜索函数返回候选列表: [(显示名, 取歌词函数或已取好的lrc文本, 优先级), ...]
# 这里统一返回 (candidate_name, fetch_lyric_callable)

def search_netease(keyword):
    """网易云搜索，返回 [(候选名, song_id), ...]"""
    url = ("https://music.163.com/api/search/get/web?csrf_token=&hlpretag=&hlposttag="
           "&s=" + urllib.parse.quote(keyword) +
           "&type=1&offset=0&total=true&limit=20")
    data = http_get_json(url, extra_headers={"Referer": "https://music.163.com"})
    songs = (data.get("result") or {}).get("songs") or []
    out = []
    for s in songs:
        artists = " ".join(a.get("name", "") for a in s.get("artists") or [])
        name = s.get("name", "")
        display = f"{name} {artists}".strip()
        out.append((display, s.get("id")))
    return out


def fetch_lyric_netease(song_id, hint=""):
    url = (f"https://music.163.com/api/song/lyric?id={song_id}"
           "&lv=1&kv=1&tv=-1")
    data = http_get_json(url, extra_headers={"Referer": "https://music.163.com"})
    lyric = ((data.get("lrc") or {}).get("lyric") or "").strip()
    return lyric


def search_kugou(keyword):
    """酷狗搜索，返回 [(候选名, hash), ...]"""
    url = ("http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword="
           + urllib.parse.quote(keyword) + "&page=1&pagesize=20")
    data = http_get_json(url)
    info = (data.get("data") or {}).get("info") or []
    out = []
    for s in info:
        display = f"{s.get('songname','')} {s.get('singername','')}".strip()
        out.append((display, s.get("hash")))
    return out


def fetch_lyric_kugou(song_hash, hint=""):
    """按 hash 查歌词。酷狗的候选里常混入无关歌曲（如 June-Barcarole 垃圾数据），
    因此用候选歌名/歌手与 hint 的相似度挑最匹配的，差异过大则返回空。"""
    url = ("http://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword=&duration="
           "&hash=" + urllib.parse.quote(song_hash))
    data = http_get_json(url)
    candidates = (data.get("candidates") or [])
    if not candidates:
        return ""
    if hint:
        # 在歌词候选中挑与目标最匹配的一个
        scored = []
        for c in candidates:
            song = c.get("song") or ""
            singer = c.get("singer") or ""
            s = max(similarity(hint, song + " " + singer),
                    similarity(hint, song))
            scored.append((s, c))
        scored.sort(key=lambda x: -x[0])
        best_score, c = scored[0]
        if best_score < 0.2:
            return ""  # 候选全都不像目标，宁缺毋滥
    else:
        c = candidates[0]
    dl = ("http://lyrics.kugou.com/download?ver=1&client=pc&id={id}&accesskey={key}"
          "&fmt=lrc&charset=utf8").format(id=c["id"], key=urllib.parse.quote(c["accesskey"]))
    d2 = http_get_json(dl)
    content = (d2.get("content") or "")
    if not content:
        return ""
    return base64.b64decode(content).decode("utf-8", errors="ignore").strip()


def search_qq(keyword):
    """QQ 音乐搜索，返回 [(候选名, songmid), ...]"""
    url = ("https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w="
           + urllib.parse.quote(keyword) + "&n=20&format=json")
    data = http_get_json(url, extra_headers={"Referer": "https://y.qq.com"})
    body = data.get("data") or {}
    songs = ((body.get("song") or {}).get("list")) or []
    out = []
    for s in songs:
        singers = " ".join(x.get("name", "") for x in s.get("singer") or [])
        display = f"{s.get('songname','')} {singers}".strip()
        out.append((display, s.get("songmid")))
    return out


def fetch_lyric_qq(songmid, hint=""):
    url = (f"https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
           f"?songmid={songmid}&g_tk=5381&format=json&nobase64=1")
    data = http_get_json(url, extra_headers={"Referer": "https://y.qq.com"})
    lyric = (data.get("lyric") or "").strip()
    if not lyric:
        return ""
    # nobase64=1 失败时兜底再试 base64
    if lyric.startswith("ey") or "\\u" not in lyric and looks_base64(lyric):
        try:
            lyric = base64.b64decode(lyric).decode("utf-8", errors="ignore").strip()
        except Exception:
            pass
    return lyric


def looks_base64(s):
    try:
        base64.b64decode(s, validate=True)
        return True
    except Exception:
        return False


PROVIDERS = [
    ("网易云", search_netease, fetch_lyric_netease),
    ("酷狗",   search_kugou,   fetch_lyric_kugou),
    ("QQ音乐", search_qq,      fetch_lyric_qq),
]


# ---------------------------------------------------------------- 匹配与下载

def collect_candidates(target_name, keywords, log):
    """在各接口搜索，返回按相似度降序的候选列表 [(score, pname, fetch, display), ...]"""
    all_cands = []  # (score, pname, fetch, display)
    for pname, search_fn, fetch_fn in PROVIDERS:
        for kw in keywords:
            try:
                candidates = search_fn(kw)
            except Exception as e:
                log(f"    [{pname}] 搜索 '{kw}' 失败: {e}")
                continue
            for display, ref in candidates:
                if not ref:
                    continue
                score = max(
                    similarity(target_name, display),
                    similarity(target_name.replace(" ", ""), display.replace(" ", "")),
                )
                fetch = (lambda f=fetch_fn, r=ref, d=display: f(r, d))
                all_cands.append((score, pname, fetch, display))
    # 去重（同接口同候选名），保留最高分
    seen = {}
    for score, pname, fetch, display in all_cands:
        key = (pname, normalize(display))
        if key not in seen or score > seen[key][0]:
            seen[key] = (score, pname, fetch, display)
    out = sorted(seen.values(), key=lambda x: -x[0])
    for c in out[:3]:
        log(f"    [{c[1]}] 候选 {c[0]:.2f}: {c[3]}")
    return out


def is_valid_lrc(text):
    """歌词必须是带时间轴的 LRC 文本才算有效"""
    if not text or len(text) < 20:
        return False
    return bool(re.search(r"\[\d{1,2}:\d{1,2}([.:]\d{1,3})?\]", text))


def is_pure_music_notice(text):
    # 平台对纯音乐的占位提示，例如：此歌曲为没有填词的纯音乐，请您欣赏
    if not text:
        return False
    body = re.sub(r"\[[^\]]*\]", "", text).strip()
    return bool(re.search(r"没有填词|无填词|纯音乐|请欣赏|暂无歌词|instrumental", body, re.I))


# 哼唱/无意义音节字符集合
_HUMMING_CHARS = set("嗯啊哦呣唔呜嗚呃哎哎哟嘿哈啦啦啦哩啰嘀嘟嗒哔噫噯吔耶呀嘛吧呐")


def looks_like_instrumental(text):
    """
    判断歌词是否为纯音乐/哼唱识别字幕（如"嗯嗯嗯嗯the嗯"这类 AI 生成的
    无意义内容）。纯音乐没有真正的歌词，这类内容不值得保存。
    """
    if not text:
        return False
    # 去掉时间轴和标签，只保留正文
    body_lines = []
    for line in text.splitlines():
        line = re.sub(r"^\[[^\]]*\]", "", line).strip()
        if line:
            body_lines.append(line)
    if not body_lines:
        return False

    ai_pattern = re.compile(r"AI(智能)?(技术)?(生成|字幕)|本字幕由|自动生成|语音识别|TME")
    joined_all = "\n".join(body_lines)
    ai_marker = bool(ai_pattern.search(joined_all))

    # 统计"有意义内容"时排除 AI 声明行本身
    content = "\n".join(l for l in body_lines if not ai_pattern.search(l))
    cjk = re.findall(r"[\u4e00-\u9fff]", content)
    letters = re.findall(r"[A-Za-z]{2,}", content)
    if not cjk and not letters:
        return ai_marker  # 只有声明行，没有任何正文

    humming_cjk = sum(1 for c in cjk if c in _HUMMING_CHARS)
    filler = sum(1 for w in letters if w.lower() in {"the", "mm", "mmm", "oh", "ah", "la", "woo", "the"})
    total = len(cjk) + len(letters)
    meaningful = total - humming_cjk - filler
    ratio = meaningful / total if total else 0

    # AI 字幕 + 有意义内容很少 → 纯音乐哼唱
    if ai_marker and (ratio < 0.55 or meaningful < 25):
        return True
    # 无标记但内容几乎全是哼唱 → 也视为纯音乐
    if ratio < 0.25:
        return True
    return False


MAX_FETCH_ATTEMPTS = 6  # 最多尝试前 N 个候选


def download_for_file(music_path, force=False, log=print):
    base_no_ext = os.path.splitext(music_path)[0]
    lrc_path = base_no_ext + ".lrc"
    target = os.path.basename(base_no_ext)

    if os.path.exists(lrc_path) and not force:
        log(f"  跳过（已存在歌词）: {target}.lrc")
        return "skip"

    keywords = parse_name(target)
    log(f"  搜索关键词: {keywords}")

    cands = collect_candidates(target, keywords, log)
    if not cands:
        log(f"  ✗ 未找到任何候选: {target}")
        return "fail"

    # 逐个尝试（从最相似的开始），取到有效歌词即成功
    tried = 0
    only_humming = False  # 只找到哼唱/AI 字幕（纯音乐）
    for score, pname, fetch, display in cands:
        if score < FUZZY_THRESHOLD:
            break
        if tried >= MAX_FETCH_ATTEMPTS:
            break
        tried += 1
        if score < 0.999:
            log(f"    尝试模糊匹配 [{pname} {score:.2f}]: {display}")
        try:
            lyric = fetch()
        except Exception as e:
            log(f"    ✗ 获取歌词失败 [{pname}]: {e}")
            continue
        if not is_valid_lrc(lyric):
            log(f"    ✗ [{pname}] 返回内容不是有效 LRC，尝试下一个候选")
            continue
        if is_pure_music_notice(lyric):
            log(f"    · [{pname} {score:.2f}] 平台标注为纯音乐（无填词），跳过")
            only_humming = True
            continue
        if looks_like_instrumental(lyric):
            log(f"    · [{pname} {score:.2f}] 只有哼唱/AI 字幕，疑似纯音乐，跳过该候选")
            only_humming = True
            continue
        with open(lrc_path, "w", encoding="utf-8") as f:
            f.write(lyric)
        tag = "精确" if score >= 0.999 else "模糊"
        log(f"  ✓ 已保存 [{pname} {tag}匹配 相似度 {score:.2f}]: {target}.lrc")
        return "ok"

    if only_humming:
        # 若目录里存在之前误存的"占位/哼唱"歌词，顺手清理（仅限内容确为占位的文件）
        if os.path.exists(lrc_path):
            try:
                with open(lrc_path, encoding="utf-8", errors="ignore") as f:
                    old = f.read()
                if is_pure_music_notice(old) or looks_like_instrumental(old):
                    os.remove(lrc_path)
                    log(f"  已清理无效占位歌词: {target}.lrc")
            except OSError:
                pass
        log(f"  ○ 纯音乐（平台只有哼唱/占位内容，无有效歌词）: {target}")
        return "instrumental"
    log(f"  ✗ 所有候选均失败（阈值 {FUZZY_THRESHOLD}）: {target}")
    return "fail"


def iter_music_files(path, recursive=True):
    """
    列出目录（或单个文件）下的音乐文件。
    recursive=True 时递归扫描所有子目录。
    """
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return [path]
    files = []
    if recursive:
        for root, dirs, names in os.walk(path):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for n in sorted(names):
                if os.path.splitext(n)[1].lower() in MUSIC_EXTS:
                    files.append(os.path.join(root, n))
    else:
        for n in sorted(os.listdir(path)):
            full = os.path.join(path, n)
            if os.path.isfile(full) and os.path.splitext(n)[1].lower() in MUSIC_EXTS:
                files.append(full)
    return files


def main():
    ap = argparse.ArgumentParser(description="批量下载歌词 .lrc（多接口 + 模糊匹配）")
    ap.add_argument("path", nargs="?", default=".", help="音乐目录或单个音乐文件（默认当前目录）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的歌词文件")
    ap.add_argument("--quiet", action="store_true", help="只输出结果摘要")
    ap.add_argument("-r", "--recursive", action="store_true", help="递归处理所有子目录")
    args = ap.parse_args()

    target_path = os.path.abspath(args.path)
    files = iter_music_files(target_path, recursive=args.recursive)

    if not files:
        print("未找到音乐文件。")
        return

    print(f"共 {len(files)} 个音乐文件待处理"
          f"{'（含子目录）' if args.recursive else ''}\n")
    stats = {"ok": 0, "skip": 0, "fail": 0, "instrumental": 0}
    for i, f in enumerate(files, 1):
        log = (lambda *_: None) if args.quiet else print
        rel = os.path.relpath(f, target_path) if os.path.isdir(target_path) else os.path.basename(f)
        print(f"[{i}/{len(files)}] {rel}")
        try:
            stats[download_for_file(f, force=args.force, log=log)] += 1
        except Exception as e:
            print(f"  ✗ 异常: {e}")
            stats["fail"] += 1

    print(f"\n完成：成功 {stats['ok']}，纯音乐 {stats['instrumental']}，"
          f"跳过 {stats['skip']}，失败 {stats['fail']}")
    if stats["instrumental"]:
        print("（纯音乐无歌词属正常情况，已自动跳过，未生成多余文件）")


if __name__ == "__main__":
    main()
