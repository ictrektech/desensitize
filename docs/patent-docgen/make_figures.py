# -*- coding: utf-8 -*-
"""Generate patent disclosure figures (7 PNGs + figures.json with dimensions)."""
import json
import os

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

font_manager.fontManager.addfont("/System/Library/Fonts/Supplemental/Songti.ttc")
plt.rcParams["font.sans-serif"] = ["Songti SC", "STSong"]
plt.rcParams["axes.unicode_minus"] = False

ACCENT = "#1B6B7A"
FILL = "#EDF3F5"
DARK = "#16323C"
GREY = "#4A6575"
WARN = "#C89F62"
WARNF = "#FFF6E3"
SYN = "#D8E0E4"
HIT = "#F5C8C0"
LINE = "#9AB4BC"

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(OUT, exist_ok=True)
META = {}


def new_ax(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text, fill=FILL, edge=ACCENT, size=11, tcolor=DARK, lw=1.4, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4",
                                fc=fill, ec=edge, lw=lw))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=size, color=tcolor, fontweight="bold" if bold else "normal", linespacing=1.5)


def diamond(ax, cx, cy, w, h, text, size=10):
    ax.add_patch(Polygon([(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)],
                         closed=True, fc=WARNF, ec=WARN, lw=1.4))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=size, color=DARK, linespacing=1.4)


def arrow(ax, x1, y1, x2, y2, text=None, size=9, color=GREY, style="-|>", lw=1.6, dx=1.2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=14,
                                 color=color, lw=lw, shrinkA=1, shrinkB=1))
    if text:
        ax.text((x1 + x2) / 2 + dx, (y1 + y2) / 2, text, fontsize=size, color=color,
                ha="left", va="center")


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    from PIL import Image
    with Image.open(path) as im:
        META[name] = {"w": im.width, "h": im.height}


def grid_row(ax, x0, y0, cell, chars, label=None, fill_map=None, size=10):
    """Draw a character grid row; fill_map: {index: color}. Returns width."""
    for i, ch in enumerate(chars):
        fc = (fill_map or {}).get(i, "white")
        ax.add_patch(Rectangle((x0 + i * cell, y0), cell, cell, fc=fc, ec=LINE, lw=0.8))
        ax.text(x0 + i * cell + cell / 2, y0 + cell / 2, ch, ha="center", va="center",
                fontsize=size, color=DARK)
    if label:
        ax.text(x0, y0 + cell + 1.5, label, fontsize=10, color=GREY, ha="left")
    return len(chars) * cell


# ── 图1 总体架构流程 ────────────────────────────────────────────
def fig1():
    fig, ax = new_ax(12.5, 15)
    box(ax, 32, 94, 36, 5, "输入图像（base64 / 文件流）", bold=True)
    arrow(ax, 50, 94, 50, 90.4)
    box(ax, 32, 85, 36, 5, "预处理：长边受限缩放，记录缩放比")
    arrow(ax, 50, 85, 50, 81.4)
    box(ax, 26, 76, 48, 5, "OCR 检测识别：文本框四边形 + 文本 + 置信度\n（坐标按缩放比逆变换回原图坐标系）", size=10)
    arrow(ax, 50, 76, 50, 72.4)
    box(ax, 26, 67, 48, 5, "行重建：行聚类 + 行内排序 + NFKC 归一化\n构建重建文本与字符映射表 CharMap", size=10, bold=True)
    arrow(ax, 50, 67, 50, 63.4)
    box(ax, 26, 58, 48, 5, "匹配空间构造：原文空间 / 紧凑空间 / 混淆归一化空间\n（等长字符映射，共享回映射表）", size=10, bold=True)
    arrow(ax, 50, 58, 50, 54.4)
    box(ax, 26, 49, 48, 5, "三空间规则匹配：正则规则依次在各空间检索\n命中经偏移回映射至重建文本区间", size=10, bold=True)
    arrow(ax, 50, 49, 50, 45.4)
    box(ax, 26, 40, 48, 5, "校验位门控：身份证 mod11-2 / 银行卡 Luhn /\n手机号段校验，拦截归一化引入的误报", size=10, bold=True)
    arrow(ax, 50, 40, 50, 36.4)
    box(ax, 26, 31, 48, 5, "跨空间重叠判断 + 优先级排序 + 去重归并\n（空间置信顺序：原文 > 紧凑 > 归一化）", size=10, bold=True)
    arrow(ax, 50, 31, 50, 27.4)
    box(ax, 26, 22, 48, 5, "命中区间 → OCR 文本框集合（block_ids）\n可选：NER 实体经偏移映射补充人名 / 地址", size=10)
    arrow(ax, 50, 22, 50, 18.4)
    box(ax, 26, 13, 48, 5, "遮挡区域生成与多级兜底\n规则命中凸包 ∪ 字段标签邻接 ∪ 像素带补偿\n（可选触发分辨率自适应二次识别并回主流程）", size=9.5)
    arrow(ax, 50, 13, 50, 9.4)
    box(ax, 32, 4, 36, 5, "遮挡绘制 → 输出脱敏图像（+ 命中统计 / 坐标）", bold=True)
    # 旁支：场景自适应
    box(ax, 2, 43, 17, 8, "场景自适应（可选）\nOCR 文本信号 → 文档类型\n→ 规则子集与兜底策略级联", size=9, fill="#F4F8FA", edge=GREY)
    ax.add_patch(FancyArrowPatch((19, 47), (26, 51.5), arrowstyle="-|>", mutation_scale=12, color=GREY, lw=1.3))
    ax.add_patch(FancyArrowPatch((19, 47), (26, 42.5), arrowstyle="-|>", mutation_scale=12, color=GREY, lw=1.3))
    # 旁支：可逆账本
    box(ax, 81, 13, 17, 8, "可逆脱敏账本（可选）\n遮挡前裁剪像素块\nAES-256-GCM 加密配对返回", size=9, fill="#F4F8FA", edge=GREY)
    ax.add_patch(FancyArrowPatch((74, 15.5), (81, 15.5), arrowstyle="-|>", mutation_scale=12, color=GREY, lw=1.3))
    save(fig, "fig1_architecture.png")


# ── 图2 行重建与 CharMap ────────────────────────────────────────
def fig2():
    fig, ax = new_ax(13, 10)
    ax.text(2, 95, "① OCR 输出的文本框（同一行、含轻微倾斜）", fontsize=11, color=GREY)
    quads = [
        ((8, 74), (30, 76), (30, 86), (8, 84), "l38", "B0"),
        ((36, 77), (62, 79), (62, 89), (36, 87), "OOl3", "B1"),
        ((68, 80), (90, 82), (90, 92), (68, 90), "8000", "B2"),
    ]
    for p1, p2, p3, p4, txt, bid in quads:
        ax.add_patch(Polygon([p1, p2, p3, p4], closed=True,
                             fc=FILL, ec=ACCENT, lw=1.6))
        cx, cy = (p1[0] + p3[0]) / 2, (p1[1] + p3[1]) / 2
        ax.text(cx, cy, txt, ha="center", va="center", fontsize=13, color=DARK, fontweight="bold")
        ax.text(cx, cy + 5.2, bid, ha="center", fontsize=9, color=ACCENT)
    ax.text(2, 64, "② 行内按横坐标排序，块间插入合成分隔符，重建文档文本（含 doc 偏移）", fontsize=11, color=GREY)
    chars = list("l38 OOl3 8000")
    cell = 5.6
    x0 = 6
    for i, ch in enumerate(chars):
        syn = ch == " "
        ax.add_patch(Rectangle((x0 + i * cell, 50), cell, cell,
                               fc=SYN if syn else "white", ec=LINE, lw=0.9))
        if syn:
            ax.text(x0 + i * cell + cell / 2, 52.5, "合成", ha="center", va="center",
                    fontsize=6.5, color=GREY)
        else:
            ax.text(x0 + i * cell + cell / 2, 52.5, ch, ha="center", va="center",
                    fontsize=12, color=DARK, fontweight="bold")
        ax.text(x0 + i * cell + cell / 2, 47.6, str(i), ha="center", fontsize=8, color=GREY)
    ax.text(x0 + 14 * cell + 2, 52.5, "← doc 偏移", fontsize=9, color=GREY, va="center")
    ax.text(6, 43, "灰色格为合成分隔符（synthetic），不关联任何文本框", fontsize=9, color=GREY)
    ax.text(2, 36, "③ 字符映射表 CharMap（重建文本区间 ↔ 文本框编号）", fontsize=11, color=GREY)
    rows = [
        ("doc_start", "doc_end", "block_id", "synthetic"),
        ("0", "3", "0", "否"),
        ("3", "4", "—", "是（空格）"),
        ("4", "8", "1", "否"),
        ("8", "9", "—", "是（空格）"),
        ("9", "13", "2", "否"),
    ]
    tx, ty, tw, rh = 6, 22, 88, 2.2
    widths = [22, 22, 22, 42]
    for r, row in enumerate(rows):
        cx = tx
        for c, (val, w) in enumerate(zip(row, widths)):
            ax.add_patch(Rectangle((cx, ty - r * rh), w, rh, fc=FILL if r == 0 else "white",
                                   ec=LINE, lw=0.9))
            ax.text(cx + w / 2, ty - r * rh + rh / 2, val, ha="center", va="center",
                    fontsize=10, color=DARK, fontweight="bold" if r == 0 else "normal")
            cx += w
    save(fig, "fig2_rebuild_charmap.png")


# ── 图3 三空间对齐与等长回映射 ──────────────────────────────────
def fig3():
    fig, ax = new_ax(13, 10)
    cell = 5.4
    x0 = 5
    ax.text(x0, 92, "原文空间 text（13 字符，含合成分隔符）", fontsize=11, color=GREY)
    t = list("l38 OOl3 8000")
    grid_row(ax, x0, 82, cell, t, fill_map={i: SYN for i, ch in enumerate(t) if ch == " "})
    for i in range(len(t)):
        ax.text(x0 + i * cell + cell / 2, 79.2, str(i), ha="center", fontsize=8, color=GREY)

    ax.text(x0, 72, "紧凑空间 compact_text（11 字符，删除全部空白）", fontsize=11, color=GREY)
    c = list("l38OOl38000")
    grid_row(ax, x0, 62, cell, c)
    for i in range(len(c)):
        ax.text(x0 + i * cell + cell / 2, 59.2, str(i), ha="center", fontsize=8, color=GREY)

    ax.text(x0, 52, "混淆归一化空间 confused_text（11 字符，1:1 形近映射）", fontsize=11, color=GREY)
    f = list("13800138000")
    fmap = {i: HIT for i in range(11)}
    grid_row(ax, x0, 42, cell, f, fill_map=fmap)
    ax.plot([x0, x0 + 11 * cell], [38.6, 38.6], color="#C0504D", lw=2.2)
    ax.text(x0 + 11 * cell / 2, 36.4, "手机号规则命中区间 [0, 11)", fontsize=10, color="#C0504D", ha="center")

    ax.text(x0, 28, "回映射数组 compact_to_doc（紧凑偏移 → 原文偏移，等长不变量）", fontsize=11, color=GREY)
    m = [0, 1, 2, 4, 5, 6, 7, 9, 10, 11, 12]
    for i, v in enumerate(m):
        ax.add_patch(Rectangle((x0 + i * cell, 19), cell, cell, fc=FILL, ec=LINE, lw=0.9))
        ax.text(x0 + i * cell + cell / 2, 21.5, str(v), ha="center", va="center", fontsize=10, color=DARK)
    arrow(ax, x0 + 5.5 * cell, 36, x0 + 5.5 * cell, 24.6, "命中区间端点\n经数组回查", size=9, color="#C0504D")

    ax.add_patch(FancyBboxPatch((x0, 4), 40, 10, boxstyle="round,pad=0.4", fc="#FDF3F0", ec="#C0504D", lw=1.4))
    ax.text(x0 + 20, 10.6, "文档区间 = [compact_to_doc[0],\ncompact_to_doc[10]+1) = [0, 13)", ha="center", fontsize=10.5, color="#8B3A34")
    ax.text(x0 + 20, 6.2, "经 CharMap 反查 → block_ids = {0, 1, 2}", ha="center", fontsize=10.5, color="#8B3A34", fontweight="bold")
    ax.add_patch(FancyBboxPatch((58, 4), 36, 10, boxstyle="round,pad=0.4", fc=FILL, ec=ACCENT, lw=1.4))
    ax.text(76, 9, "三个 OCR 文本框全部纳入遮挡区域\n（数字被拆框 + 形近误读仍可命中）", ha="center", fontsize=10.5, color=DARK)
    arrow(ax, x0 + 40, 9, 58, 9, color=GREY)
    save(fig, "fig3_spaces_mapping.png")


# ── 图4 匹配-门控-去重流程 ─────────────────────────────────────
def fig4():
    fig, ax = new_ax(11, 15.5)
    box(ax, 28, 95, 44, 4.5, "开始：载入已启用的正则规则集", bold=True)
    arrow(ax, 50, 95, 50, 91.9)
    box(ax, 24, 87, 52, 4.5, "S401 按规则优先级降序遍历规则", size=10.5)
    arrow(ax, 50, 87, 50, 83.9)
    box(ax, 24, 79, 52, 4.5, "S402 按置信顺序遍历匹配空间：\n原文空间 → 紧凑空间 → 混淆归一化空间", size=10.5)
    arrow(ax, 50, 79, 50, 75.9)
    box(ax, 24, 71, 52, 4.5, "S403 在当前空间执行正则检索，逐一得到候选命中\n[match_start, match_end)", size=10.5)
    arrow(ax, 50, 71, 50, 67.4)
    diamond(ax, 50, 63, 34, 9, "当前空间为原文空间？", size=10)
    ax.text(68, 63, "是", fontsize=10, color=GREY)
    ax.text(33.5, 63, "否", fontsize=10, color=GREY)
    box(ax, 76, 60.7, 22, 4.5, "候选区间即文档区间", size=9.5)
    arrow(ax, 67, 63, 76, 62.9, color=GREY)
    box(ax, 2, 58.4, 22, 4.5, "等长映射回查：\n[ctd[s], ctd[e−1]+1)", size=9.5)
    arrow(ax, 33, 63, 24, 62.5, color=GREY)
    arrow(ax, 87, 60.7, 87, 55.9, color=GREY)
    arrow(ax, 13, 58.4, 13, 55.9, color=GREY)
    ax.plot([13, 44], [55.9, 55.9], color=GREY, lw=1.6)
    arrow(ax, 44, 55.9, 44, 54.4, color=GREY)
    arrow(ax, 87, 55.9, 56, 55.9, color=GREY)
    diamond(ax, 50, 49, 40, 9.5, "S404 与全部已有命中区间\n做重叠判断（区间相交）", size=10)
    ax.text(71.5, 49, "重叠 → 丢弃该候选\n（高置信空间先占）", fontsize=9, color=GREY)
    arrow(ax, 50, 44.2, 50, 41)
    diamond(ax, 50, 36, 40, 9.5, "S405 归一化空间且规则带校验器？\n是 → 提取捕获组执行校验位验证", size=9.5)
    ax.text(71.5, 36, "校验不通过 → 丢弃该候选\n（拦截归一化误报）", fontsize=9, color=GREY)
    arrow(ax, 50, 31.2, 50, 28)
    diamond(ax, 50, 23.5, 40, 8.5, "S406 文档区间经 CharMap\n能映射到至少一个文本框？", size=9.5)
    ax.text(71.5, 23.5, "空 → 丢弃", fontsize=9, color=GREY)
    arrow(ax, 50, 19.2, 50, 16)
    box(ax, 24, 11, 52, 5, "S407 记录命中：规则、占位符、文档区间、\n文本框集合、归因字段 matched_via=当前空间", size=10.5)
    arrow(ax, 76.3, 11, 86, 11, color=GREY)
    box(ax, 80, 4, 18, 7, "遍历下一候选 /\n空间 / 规则", size=9.5, fill="#F4F8FA", edge=GREY)
    arrow(ax, 86, 11, 86, 11, color=GREY)
    box(ax, 24, 2, 52, 4.5, "结束：全部命中按（文档区间起点升序，长度降序）排序输出", size=10.5, bold=True)
    save(fig, "fig4_match_gate_dedup.png")


# ── 图5 凸包遮挡几何 ────────────────────────────────────────────
def fig5():
    fig, ax = new_ax(13, 7)
    ax.text(3, 93, "现有方式：轴对齐外接矩形", fontsize=11, color=GREY)
    q1 = [(6, 62), (30, 67), (30, 79), (6, 74)]
    q2 = [(36, 70), (58, 75), (58, 87), (36, 82)]
    for q in (q1, q2):
        ax.add_patch(Polygon(q, closed=True, fc=FILL, ec=ACCENT, lw=1.6))
    ax.add_patch(Rectangle((6, 62), 52, 25, fc="none", ec="#C0504D", lw=1.8, ls="--"))
    ax.text(32, 56, "外接矩形同时覆盖上下相邻内容（过度遮挡）", fontsize=10, color="#8B3A34", ha="center")

    ax.text(62, 93, "本发明：外扩顶点 + 凸包", fontsize=11, color=GREY)
    q3 = [(66, 62), (90, 67), (90, 79), (66, 74)]
    q4 = [(96, 70), (95, 75), (95, 87), (96, 82)]
    q4 = [(94 - 28, 70), (95 - 28, 75), (95 - 28, 87), (94 - 28, 82)]
    # 用右侧独立两框
    q3 = [(64, 62), (86, 67), (86, 79), (64, 74)]
    q4 = [(90, 70), (97, 72), (97, 84), (90, 82)]
    import math
    pts = []
    for q in (q3, q4):
        cx = sum(p[0] for p in q) / 4
        cy = sum(p[1] for p in q) / 4
        exp = []
        for px, py in q:
            dx, dy = px - cx, py - cy
            ln = math.hypot(dx, dy) or 1.0
            exp.append((px + dx / ln * 2.2, py + dy / ln * 2.2))
            pts.append(exp[-1])
        ax.add_patch(Polygon(exp, closed=True, fc="none", ec=GREY, lw=1.0, ls=":"))
    ax.add_patch(Polygon(sorted(pts), closed=True, fc="#E8A79E", ec="#8B3A34", lw=2.4, alpha=0.85))
    for q in (q3, q4):
        ax.add_patch(Polygon(q, closed=True, fc=FILL, ec=ACCENT, lw=1.6))
    ax.text(81, 56, "凸包贴合倾斜文本，遮挡面积显著减小", fontsize=10, color=DARK, ha="center")
    ax.text(50, 40, "构造步骤：① 取命中文本框组的各实际四边形顶点 → ② 每个顶点沿「顶点→质心」反方向外扩固定像素 → ③ 对外扩后顶点集取凸包 → ④ 凸包多边形作为遮挡区域，其外接框仅用于坐标上报与去重键",
            fontsize=10.5, color=DARK, ha="center")
    ax.plot([5, 95], [48, 48], color=LINE, lw=1)
    save(fig, "fig5_hull_masking.png")


# ── 图6 场景自适应级联 ──────────────────────────────────────────
def fig6():
    fig, ax = new_ax(12, 9)
    box(ax, 4, 88, 26, 7, "OCR 文本框集合\n（字段标签 / 关键词信号）", size=10.5)
    arrow(ax, 30, 91.5, 38, 91.5)
    box(ax, 38, 88, 26, 7, "信号统计\n身份证件 / 发票 / 物流面单 /\n配置截图 各场景信号计数", size=9.5)
    arrow(ax, 64, 91.5, 72, 91.5)
    diamond(ax, 84, 91.5, 24, 10, "最高计数 ≥ 2 且\n严格领先次高？", size=9.5)
    ax.text(72.5, 84, "否 → 通用场景（全量规则 + 全部兜底，保证不漏遮）", fontsize=9.5, color=GREY)
    arrow(ax, 84, 86.5, 84, 80)
    rows = [
        ("场景类型", "规则类别子集", "字段标签兜底", "像素带兜底", "NER 提示"),
        ("身份证件", "全量", "开", "开", "开"),
        ("发票 / 票据", "全量", "开", "开", "关"),
        ("物流面单", "全量", "开", "开", "开"),
        ("配置截图", "api_key + pii", "关", "开", "关"),
        ("通用（回退）", "全量", "开", "开", "开"),
    ]
    tx, ty, rh = 8, 72, 5.2
    widths = [16, 20, 17, 17, 14]
    for r, row in enumerate(rows):
        cx = tx
        for val, w in zip(row, widths):
            fc = FILL if r == 0 else ("#FDF6EC" if r == 4 and val == "api_key + pii" else "white")
            ax.add_patch(Rectangle((cx, ty - r * rh), w, rh, fc=fc, ec=LINE, lw=0.9))
            ax.text(cx + w / 2, ty - r * rh + rh / 2, val, ha="center", va="center",
                    fontsize=9.5, color=DARK, fontweight="bold" if r == 0 else "normal")
            cx += w
    ax.text(50, 40, "策略级联执行：规则子集过滤 → 三空间匹配 + 校验门控 + 跨空间去重 → 按需启停两级兜底遮挡",
            fontsize=10.5, color=DARK, ha="center")
    arrow(ax, 50, 46, 50, 35)
    box(ax, 22, 26, 56, 7, "输出：脱敏图像 + 场景判定结果（metadata.scene）\n信号不足或并列时回退通用策略（漏遮安全侧）", size=10.5)
    save(fig, "fig6_adaptive_cascade.png")


# ── 图7 可逆账本时序 ────────────────────────────────────────────
def fig7():
    fig, ax = new_ax(13, 7.5)
    box(ax, 2, 88, 20, 8, "调用方\n（持 32 字节密钥）", size=10.5)
    box(ax, 40, 88, 20, 8, "脱敏服务", size=10.5, bold=True)
    box(ax, 78, 88, 20, 8, "加密账本\n（随响应返回）", size=10.5)
    ax.plot([12, 12], [84, 8], color=LINE, lw=1.2, ls="--")
    ax.plot([50, 50], [84, 8], color=LINE, lw=1.2, ls="--")
    ax.plot([88, 88], [84, 8], color=LINE, lw=1.2, ls="--")
    steps = [
        (12, 50, 78, "① 脱敏请求（reversible=true，密钥或密钥引用）"),
        (50, 88, 68, "② 遮挡前：逐区域裁剪原始像素块，PNG 无损序列化"),
        (50, 88, 55, "③ AES-256-GCM 加密：每区域独立随机 nonce，区域序号作 AAD"),
        (50, 88, 42, "④ 生成账本条目 {区域序号, 外接框, nonce, 密文}，与脱敏图配对返回"),
        (12, 50, 29, "⑤ 还原请求（脱敏图 + 账本 + 密钥）"),
        (50, 88, 16, "⑥ 逐区域解密贴回（含 1px 边缘余量补偿），单区域失败不中断"),
    ]
    for x1, x2, y, text in steps:
        ax.add_patch(FancyArrowPatch((x1, y), (x2, y), arrowstyle="-|>", mutation_scale=13,
                                     color=ACCENT if x1 == 50 else GREY, lw=1.6))
        ax.text(50, y + 2.2, text, fontsize=9.8, color=DARK, ha="center")
    ax.text(50, 6, "账本不含明文；无密钥方无法还原，有密钥方可像素级无损恢复（独立发明构思，建议单独申请）",
            fontsize=10, color="#8B3A34", ha="center")
    save(fig, "fig7_reversible_ledger.png")


fig1()
fig2()
fig3()
fig4()
fig5()
fig6()
fig7()
with open(os.path.join(OUT, "figures.json"), "w", encoding="utf-8") as fp:
    json.dump(META, fp, ensure_ascii=False, indent=1)
print("figures:", len(META))
for k, v in META.items():
    print(k, v)
