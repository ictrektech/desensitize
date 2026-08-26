/* 专利技术交底书生成脚本 — docx-js */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  ImageRun, PageBreak, Header, Footer, PageNumber, NumberFormat,
  AlignmentType, HeadingLevel, WidthType, BorderStyle, ShadingType,
  SectionType, TableOfContents, TableLayoutType, LevelFormat,
} = require("docx");

const FIG = JSON.parse(fs.readFileSync(path.join(__dirname, "figures", "figures.json"), "utf8"));
const OUT = path.resolve(__dirname, "..", "专利交底书_图像敏感信息识别与遮挡_20260819.docx");

/* ── 调色（DM-1 深青，技术类） ── */
const P = {
  bg: "162235", titleColor: "FFFFFF", subtitleColor: "B0B8C0",
  metaColor: "90989F", accent: "37DCF2", footerColor: "687078",
  headPrimary: "0A1628", body: "000000", secondary: "5B6B7D",
  tHead: "1B6B7A", tInner: "C8DDE2", tSurface: "EDF3F5", codeBg: "F4F6F8",
};

const NB = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noBorders = { top: NB, bottom: NB, left: NB, right: NB };
const allNoBorders = { top: NB, bottom: NB, left: NB, right: NB, insideHorizontal: NB, insideVertical: NB };

/* ── 通用构件 ── */
function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160, line: 312 },
    children: [new TextRun({ text, bold: true, size: 32, color: P.headPrimary, font: { ascii: "Times New Roman", eastAsia: "SimHei" } })],
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 260, after: 120, line: 312 },
    children: [new TextRun({ text, bold: true, size: 28, color: P.headPrimary, font: { ascii: "Times New Roman", eastAsia: "SimHei" } })],
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 200, after: 100, line: 312 },
    children: [new TextRun({ text, bold: true, size: 24, color: P.headPrimary, font: { ascii: "Times New Roman", eastAsia: "SimHei" } })],
  });
}
function p(text, opts = {}) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 312, after: opts.after || 60 },
    children: [new TextRun({ text, size: 24, color: P.body, font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
  });
}
function pBold(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: 480 },
    spacing: { line: 312, after: 60 },
    children: [new TextRun({ text, size: 24, bold: true, color: P.body, font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
  });
}
function note(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { left: 480, right: 480 },
    spacing: { line: 300, before: 80, after: 120 },
    border: { left: { style: BorderStyle.SINGLE, size: 12, color: P.tHead, space: 10 } },
    children: [new TextRun({ text, size: 21, color: P.secondary, font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
  });
}
function pc(lines) {
  return lines.map((line, i) => new Paragraph({
    alignment: AlignmentType.LEFT,
    indent: { left: 360 },
    spacing: { line: 264, before: i === 0 ? 80 : 0, after: i === lines.length - 1 ? 120 : 0 },
    shading: { type: ShadingType.CLEAR, fill: P.codeBg },
    children: [new TextRun({ text: line.length ? line : " ", size: 18, color: "1C2A33", font: { ascii: "Courier New", eastAsia: "SimSun" } })],
  }));
}
function tcap(text) {
  return new Paragraph({
    keepNext: true,
    alignment: AlignmentType.CENTER,
    spacing: { before: 160, after: 80 },
    children: [new TextRun({ text, bold: true, size: 21, color: P.headPrimary, font: { ascii: "Times New Roman", eastAsia: "SimHei" } })],
  });
}
function cellPara(text, bold, color, align) {
  return new Paragraph({
    alignment: align || AlignmentType.LEFT,
    spacing: { line: 276 },
    children: [new TextRun({ text: String(text), bold: !!bold, size: 20, color: color || P.body, font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
  });
}
function tbl(headers, rows, widths, aligns) {
  const mkRow = (cells, isHead) => new TableRow({
    tableHeader: !!isHead,
    cantSplit: true,
    children: cells.map((c, i) => new TableCell({
      children: [cellPara(c, isHead, isHead ? "FFFFFF" : P.body, (aligns && aligns[i]) || AlignmentType.LEFT)],
      shading: { type: ShadingType.CLEAR, fill: isHead ? P.tHead : "FFFFFF" },
      margins: { top: 60, bottom: 60, left: 120, right: 120 },
      width: { size: widths[i], type: WidthType.PERCENTAGE },
    })),
  });
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: P.tHead },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: P.tHead },
      left: NB, right: NB,
      insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: P.tInner },
      insideVertical: NB,
    },
    rows: [mkRow(headers, true), ...rows.map(r => mkRow(r, false))],
  });
}
function figure(name, caption, displayWidth) {
  const meta = FIG[name];
  const w = displayWidth || 560;
  const h = Math.round(w * meta.h / meta.w);
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 160, after: 40 },
      keepNext: true,
      children: [new ImageRun({
        data: fs.readFileSync(path.join(__dirname, "figures", name)),
        transformation: { width: w, height: h },
        type: "png",
      })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 160 },
      children: [new TextRun({ text: caption, bold: true, size: 21, color: P.headPrimary, font: { ascii: "Times New Roman", eastAsia: "SimHei" } })],
    }),
  ];
}
function pageNumFooter() {
  return new Footer({
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: P.secondary })],
    })],
  });
}
function docHeader() {
  return new Header({
    children: [new Paragraph({
      alignment: AlignmentType.RIGHT,
      border: { bottom: { style: BorderStyle.SINGLE, size: 2, color: P.tInner, space: 4 } },
      children: [new TextRun({ text: "专利技术交底书（内部保密）", size: 18, color: P.secondary, font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
    })],
  });
}

/* ── 封面（R1 配方） ── */
function calcTitleLayout(title, maxWidthTwips, preferredPt = 40, minPt = 24) {
  const charsPerLine = pt => Math.floor(maxWidthTwips / (pt * 20));
  let titlePt = preferredPt, lines;
  const split = (t, cpl) => {
    const breakAfter = new Set([...":,;.、;:!?", ...":的与和及之在于为", ..."-_/ "]);
    const out = []; let rem = t;
    while (rem.length > cpl) {
      let at = -1;
      for (let i = cpl; i >= Math.floor(cpl * 0.6); i--) if (i < rem.length && breakAfter.has(rem[i - 1])) { at = i; break; }
      if (at === -1) at = cpl;
      out.push(rem.slice(0, at).trim()); rem = rem.slice(at).trim();
    }
    if (rem) out.push(rem);
    if (out.length > 1 && out[out.length - 1].length <= 2) { const last = out.pop(); out[out.length - 1] += last; }
    return out;
  };
  while (titlePt >= minPt) {
    const cpl = charsPerLine(titlePt);
    if (cpl < 2) { titlePt -= 2; continue; }
    lines = split(title, cpl);
    if (lines.length <= 3) break;
    titlePt -= 2;
  }
  if (!lines || lines.length > 3) { lines = split(title, charsPerLine(minPt)); titlePt = minPt; }
  return { titlePt, titleLines: lines };
}
function calcCoverSpacing(prm) {
  const { titleLineCount = 1, titlePt = 36, hasSubtitle = false, hasEnglishLabel = false,
    metaLineCount = 0, fixedHeight = 800, pageHeight = 16838 } = prm;
  const SAFETY = 1200;
  const usable = pageHeight - SAFETY;
  const contentH = titleLineCount * (titlePt * 23 + 200) + (hasSubtitle ? (12 * 23 + 600) : 0) +
    (hasEnglishLabel ? (9 * 23 + 600) : 0) + metaLineCount * (10 * 23 + 100) + fixedHeight + 3 * 300;
  const remain = Math.max(usable - contentH, 400);
  const FOOTER_MIN = 800;
  const rawTop = Math.floor(remain * 0.45), rawBottom = Math.floor(remain * 0.45);
  const bottomSpacing = Math.max(rawBottom, FOOTER_MIN);
  const topSpacing = Math.max(rawTop - Math.max(0, FOOTER_MIN - rawBottom), 400);
  return { topSpacing, bottomSpacing };
}
function buildCoverR1(config) {
  const padL = 1200, padR = 800;
  const availableWidth = 11906 - padL - padR - 300;
  const { titlePt, titleLines } = calcTitleLayout(config.title, availableWidth, 40, 24);
  const titleSize = titlePt * 2;
  const spacing = calcCoverSpacing({
    titleLineCount: titleLines.length, titlePt,
    hasSubtitle: !!config.subtitle, hasEnglishLabel: !!config.englishLabel,
    metaLineCount: (config.metaLines || []).length, fixedHeight: 400,
  });
  const accentLeft = { style: BorderStyle.SINGLE, size: 8, color: P.accent, space: 12 };
  const children = [];
  children.push(new Paragraph({ spacing: { before: spacing.topSpacing } }));
  if (config.englishLabel) {
    children.push(new Paragraph({
      indent: { left: padL, right: padR }, spacing: { after: 500 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: P.accent, space: 8 } },
      children: [new TextRun({ text: config.englishLabel.split("").join("  "), size: 18, color: P.accent, font: { ascii: "Calibri", eastAsia: "SimHei" }, characterSpacing: 40 })],
    }));
  }
  for (let i = 0; i < titleLines.length; i++) {
    children.push(new Paragraph({
      indent: { left: padL },
      spacing: { after: i < titleLines.length - 1 ? 100 : 300, line: Math.ceil(titlePt * 23), lineRule: "atLeast" },
      children: [new TextRun({ text: titleLines[i], size: titleSize, bold: true, color: P.titleColor, font: { eastAsia: "SimHei", ascii: "Arial" } })],
    }));
  }
  if (config.subtitle) {
    children.push(new Paragraph({
      indent: { left: padL }, spacing: { after: 800 },
      children: [new TextRun({ text: config.subtitle, size: 24, color: P.subtitleColor, font: { eastAsia: "Microsoft YaHei", ascii: "Arial" } })],
    }));
  }
  for (const line of (config.metaLines || [])) {
    children.push(new Paragraph({
      indent: { left: padL + 200 }, spacing: { after: 80 },
      border: { left: accentLeft },
      children: [new TextRun({ text: line, size: 24, color: P.metaColor, font: { eastAsia: "Microsoft YaHei", ascii: "Arial" } })],
    }));
  }
  children.push(new Paragraph({ spacing: { before: spacing.bottomSpacing } }));
  children.push(new Paragraph({
    indent: { left: padL, right: padR },
    border: { top: { style: BorderStyle.SINGLE, size: 2, color: P.accent, space: 8 } },
    spacing: { before: 200 },
    children: [
      new TextRun({ text: config.footerLeft || "", size: 16, color: P.footerColor, font: { ascii: "Arial" } }),
      new TextRun({ text: "                                        " }),
      new TextRun({ text: config.footerRight || "", size: 16, color: P.footerColor, font: { ascii: "Arial" } }),
    ],
  }));
  return [new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    layout: TableLayoutType.FIXED,
    borders: allNoBorders,
    rows: [new TableRow({
      height: { value: 16838, rule: "exact" },
      children: [new TableCell({
        shading: { type: ShadingType.CLEAR, fill: P.bg }, borders: noBorders,
        children,
      })],
    })],
  })];
}

/* ════════════════════ 正文内容 ════════════════════ */
const B = [];

/* 一、发明名称 */
B.push(h1("一、发明名称"));
B.push(p("一种基于多匹配空间与多级兜底的图像敏感信息识别与遮挡方法及系统（暂定名，可由代理人按检索情况调整）。"));

/* 二、技术领域 */
B.push(h1("二、技术领域"));
B.push(p("本发明涉及数据安全与图像处理技术领域，具体涉及一种对包含敏感信息（个人身份信息、联系方式、金融账号、密钥凭证、票据单号等）的图像进行自动识别、定位与遮挡（脱敏）的方法及系统，尤其涉及基于光学字符识别（OCR）输出重建文本并构造多个匹配空间执行敏感信息检索、并通过校验位门控与跨空间去重保证召回率与精确率的技术。"));

/* 三、背景技术 */
B.push(h1("三、背景技术"));
B.push(h2("3.1 现有技术状况"));
B.push(p("图像敏感信息脱敏的通用技术路线为：先对图像执行 OCR 得到文本框（含文本内容与坐标），再在文本内容上执行敏感信息识别（正则规则、命名实体识别模型或云服务的检测器），最后在对应文本框坐标处绘制遮挡（涂黑、马赛克等）。代表性现有方案包括："));
B.push(p("（1）云服务商图像检查与隐去服务：对图像执行 OCR 后按预定义信息类型检测器识别敏感项并在其位置隐去，部分检测器内置校验和验证以降低误报；"));
B.push(p("（2）开源隐私保护框架：以正则识别器配合 Luhn 校验过滤银行卡误报，并提供图像脱敏组件，对图像 OCR 后在其文本框上绘制矩形遮挡；"));
B.push(p("（3）中国专利 CN113128504A 提出一种基于校验规则的 OCR 识别结果纠错方法：按预设替换字符集对识别结果中不符合字段类型规则的字符做形近替换，并用校验位（如证件机读码的加权模 10 校验）验证替换正确性，用于输出纠错后的识别文本；"));
B.push(p("（4）开源工具与学术方案：基于 OCR 文本行四点框生成跟随倾斜的遮挡区域（如 midecal_tool）；基于文本区域凸包并结合条件随机场细化生成隐私遮挡区域（CVPR 2018 论文 Connecting Pixels to Privacy and Utility）。"));
B.push(h2("3.2 现有技术存在的缺陷"));
B.push(p("经分析，现有技术在真实图像（证件、票据、物流面单、聊天截图、配置截图等，常为手机拍摄、倾斜、低对比度）场景下存在如下具体技术缺陷："));
B.push(p("缺陷一：OCR 输出碎片化导致漏检。OCR 引擎常将一个完整敏感值拆分为多个文本框，且在块间引入空格或换行；在孤立文本框上执行正则匹配必然漏检。现有方案普遍缺乏将碎片重组为连续文本并保留字符级坐标回溯能力的机制。"));
B.push(p("缺陷二：数字被误读为形近字母导致漏检。低质量图像上 OCR 常将 0 认作 O 或 o、1 认作 l 或 I、5 认作 S、8 认作 B 等。此时即便重组了文本，正则规则（面向纯数字格式）仍然无法命中。现有云服务与开源框架均直接在原始识别文本上匹配，缺乏对此类系统性误读的检索手段；即便事后以校验和验证，也因候选本身不满足格式而无法进入验证环节。"));
B.push(p("缺陷三：字符替换类纠错与遮挡脱敏的目标错配。CN113128504A 的形近替换以纠正识别结果为目的，作用于字符串层：其先检错（字符类型不符合字段规则）再对错误字符做替换并复核。该方案不构造面向脱敏的匹配空间，不维护字符与图像坐标的映射，命中结果无法定位回图像执行遮挡，也没有多候选空间之间的置信排序与去重机制，无法直接用于图像脱敏。"));
B.push(p("缺陷四：遮挡区域形状与兜底能力不足。轴对齐外接矩形对倾斜文本过度遮挡相邻内容；OCR 整行漏检时长密钥串像素被原样返回；数字拆断时缺乏版式语义（字段标签）层面的兜底。"));
B.push(p("缺陷五：单一策略无法兼顾不同版式的召回与误遮。配置截图中的长字母数字串会被单据类规则泛化误遮，而单据类图片又需要全量规则与兜底，现有方案缺乏按文档类型级联调整策略的轻量机制。"));

/* 四、发明内容 */
B.push(h1("四、发明内容"));
B.push(h2("4.1 发明目的"));
B.push(p("针对上述缺陷，本发明的目的在于提供一种图像敏感信息识别与遮挡方法及系统，使 OCR 碎片化、数字形近误读两类系统性漏检被显式检索机制覆盖，并通过校验位门控控制由此引入的误报、通过跨空间置信去重避免重复计数，最终在不引入额外重型模型（适配边缘弱性能设备）的前提下，同时提升图像脱敏的召回率与遮挡精确度。"));
B.push(h2("4.2 总体技术方案"));
B.push(p("本发明的总体处理流程如图 1 所示，包含十个阶段：S101 输入图像；S102 预处理（长边受限缩放并记录缩放比）；S103 OCR 检测识别得到文本框四边形、文本与置信度，坐标按缩放比逆变换回原图坐标系；S104 行重建并构建重建文本与字符映射表（字符区间与文本框编号的映射关系，见 5.1）；S105 构造三个匹配空间：原文空间、紧凑空间、混淆归一化空间（三者通过等长字符映射共享回映射表，见 5.2）；S106 三空间规则匹配并经偏移回映射至重建文本区间；S107 校验位门控，拦截归一化引入的误报（见 5.3）；S108 跨空间区间重叠判断、优先级排序与去重归并（见 5.4）；S109 命中区间映射为文本框集合并生成遮挡区域（凸包精确遮挡，见 5.5），叠加多级兜底（字段标签邻接兜底、像素带补偿兜底与分辨率自适应二次识别兜底，见 5.6），可选叠加文档类型自适应策略级联（见 5.7）；S110 遮挡绘制并输出脱敏图像及命中统计。可选地，在遮挡前生成可逆脱敏账本（见 5.8）。"));
B.push(...figure("fig1_architecture.png", "图 1  总体处理流程与模块关系", 540));
B.push(note("图 1 中加粗框为本发明相对现有技术的核心创新环节（行重建映射表、三空间构造、校验位门控、跨空间去重）；右侧两个虚线框为可选旁路（场景自适应、可逆账本），均可独立启停。"));

/* 五、关键技术方案 */
B.push(h1("五、关键技术方案详述"));
B.push(h2("5.1 OCR 文本框行重建与字符-文本框位置映射关系的建立"));
B.push(p("本节解决的核心问题是：如何在将碎片化 OCR 输出重组为连续可匹配文本的同时，保留每一个字符到其来源文本框的可回溯映射关系，使后续任意匹配空间中的命中都能精确定位回图像坐标执行遮挡。具体步骤如下（S201 至 S206）："));
B.push(pBold("S201（文本框接收与规整）：接收 OCR 引擎输出的 N 个文本框，每个文本框包含文本串、四边形顶点（按原图坐标系）、轴对齐外接框及识别置信度。过滤文本为空或全空白的文本框；对外接框存在而四边形缺失的文本框，由外接框四角生成正向四边形补全；对保留下来的文本框按顺序赋予全局唯一编号 block_id。"));
B.push(pBold("S202（行聚类）：将全部文本框按（外接框垂直中心 cy，外接框左边缘 x1）升序排序后逐个归行。对当前文本框 b 与已有行 L 的归行判据为："));
B.push(...pc([
  "T = max( 8px, 0.65 * h_b, mean(0.65 * h_i for i in L) )   // 自适应行阈值",
  "若 |cy_b - mean(cy_i for i in L)| <= T，则 b 归入行 L（取首个满足的行）；",
  "否则新建一行。",
]));
B.push(p("其中 h 为外接框高度。阈值同时考虑当前框高度与该行已有框高度，使同一行文本即使字号差异较大（如标签小字与数值大字）仍可归并，而上下两行相邻文本因垂直中心距离超过阈值而正确分离。8 像素下限避免极小框导致阈值退化。"));
B.push(pBold("S203（行内排序）：对每行内的文本框按外接框左边缘 x1 升序排序，赋予行编号 line_id，恢复阅读顺序。"));
B.push(pBold("S204（文本归一化）：对每个文本框的文本执行 Unicode NFKC 归一化（全角数字字母转半角、兼容分解等），消除全半角混排对正则匹配的干扰。"));
B.push(pBold("S205（重建文档文本）：按行序、行内序拼接生成重建文档文本 text：行内相邻文本框之间插入一个空格作为合成分隔符；非末行的行尾插入一个换行符作为合成分隔符。合成分隔符的意义：保持自然语言可读性以供命名实体识别模型使用，同时在紧凑空间中被整体删除以还原跨框连续敏感值。"));
B.push(pBold("S206（构建字符映射表 CharMap）：在拼接过程中逐字符区间登记映射记录 CharMap = { doc_start, doc_end, block_id, synthetic }，其中 doc_start 与 doc_end 为该字符区间在重建文本中的偏移（左闭右开），block_id 为来源文本框编号，synthetic 标记该区间是否为合成分隔符（合成区间 block_id 为空）。"));
B.push(p("以图 2 为例：三个文本框 B0=l38、B1=OOl3、B2=8000 位于同一行，重建文本为 13 字符，其中偏移 3 与 8 为合成分隔符；CharMap 共 5 条记录（表 1 与图 2 下部一致）。"));
B.push(...figure("fig2_rebuild_charmap.png", "图 2  行重建与字符映射表 CharMap 的构建", 560));
B.push(tcap("表 1  CharMap 记录示例（对应图 2）"));
B.push(tbl(["doc_start", "doc_end", "block_id", "synthetic（合成标记）", "内容"],
  [["0", "3", "0", "否", "l38"],
   ["3", "4", "—", "是（块间空格）", "空格"],
   ["4", "8", "1", "否", "OOl3"],
   ["8", "9", "—", "是（块间空格）", "空格"],
   ["9", "13", "2", "否", "8000"]],
  [14, 14, 14, 30, 28], [AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.LEFT, AlignmentType.LEFT]));
B.push(p("由文档区间反查文本框集合的算法（记为 span_to_block_ids）：遍历 CharMap，跳过 synthetic 为真的记录；保留满足「doc_end 大于区间起点 且 doc_start 小于区间终点」的记录（即与查询区间相交），按出现顺序输出去重后的 block_id 列表。伪代码如下："));
B.push(...pc([
  "function span_to_block_ids(rebuilt, start, end):",
  "    ids = []; seen = empty set",
  "    for m in rebuilt.char_maps:",
  "        if m.synthetic or m.block_id is None: continue     // 跳过合成分隔符",
  "        if m.doc_end <= start or m.doc_start >= end: continue  // 不相交",
  "        if m.block_id not in seen:",
  "            seen.add(m.block_id); ids.append(m.block_id)",
  "    return ids   // 命中区间覆盖到的全部来源文本框",
]));
B.push(p("该映射关系是后续全部机制的基础：任何匹配空间中的命中，最终都经由「空间内偏移到文档区间、文档区间经 CharMap 到文本框集合」两级映射回到图像坐标。"));
B.push(h3("5.1.1 位置映射的技术特点与工程强化"));
B.push(p("（1）码点级偏移与字素安全：全部偏移按 Unicode 码点而非字节计算，多字节字符（中文、全角符号等）与组合字符不会造成区间错位；NFKC 归一化在登记映射前完成，保证匹配所见字符与映射登记字符完全一致。"));
B.push(p("（2）块级倒排索引：除文档区间到文本框的正查外，同步维护文本框编号到其文档区间的倒排索引（每框至多一条非合成记录）。字段标签邻接兜底取「标签框同行右侧区间」、命名实体识别结果对齐取「实体区间覆盖的框」均走倒排索引直达，无需线性扫描字符映射表。"));
B.push(p("（3）流式线性构建与常数空间开销：行重建与映射登记在一次遍历中同步完成，时间复杂度为文本框总数的线性量级叠加文本总长；字符映射表按块聚合登记（每框一条非合成记录加固定数量合成记录），空间开销与文本框数线性相关，与逐字符登记相比显著压缩，适配边缘设备内存约束。"));
B.push(p("（4）行分组键内嵌：命中的文本框集合天然携带行编号信息（文本框在行重建时已标注 line_id），跨行命中（如被表格线打断的长账号）在遮挡区域生成阶段自动按行分组、分行生成遮挡区域，避免跨行合并框覆盖中间无关内容。"));

B.push(h2("5.2 多匹配空间构造与等长字符映射的位置回映射"));
B.push(p("本节解决的核心问题是：如何让格式敏感的正则规则能够命中「被合成分隔符切断」与「数字被形近字母替换」两类受损文本，同时使任意空间中的命中都能无歧义地回映射到 5.1 建立的文档坐标系。本发明构造三个匹配空间（S301 至 S305）："));
B.push(pBold("S301（原文空间 text）：即 5.1 重建的文档文本本身。保留空格与换行，匹配语义与自然语言一致；该空间置信级最高。"));
B.push(pBold("S302（紧凑空间 compact_text 与回映射数组）：将 text 中全部 Unicode 空白字符删除得到 compact_text；在删除的同时构造回映射数组 compact_to_doc，其中 compact_to_doc[i] 为紧凑文本第 i 个字符在原文空间中的偏移。由构造过程可知 compact_text 与 compact_to_doc 严格等长且一一对应。该空间解决缺陷一（碎片化切断），置信级居中。"));
B.push(pBold("S303（混淆归一化空间 confused_text）：对 compact_text 逐字符应用形近字符映射表（表 2）得到 confused_text，仅将可能被误读为数字的形近字母映射为数字，其余字符保持不变。该空间解决缺陷二（形近误读），置信级最低，仅对绑定校验器的规则启用（见 5.3）。"));
B.push(tcap("表 2  混淆字符映射表（默认实施例）"));
B.push(tbl(["映射源字符", "映射目标字符", "说明"],
  [["O、o", "0", "字母 O 常被误读为数字 0 的反向情形"],
   ["l、I、i", "1", "竖线形字母与数字 1 互为形近"],
   ["Z、z", "2", "手写与低分辨率场景常见混淆"],
   ["S、s", "5", "低对比度图像常见混淆"],
   ["G", "6", "印刷体形近"],
   ["B", "8", "印刷体形近"],
   ["g", "9", "印刷体形近"]],
  [20, 20, 60], [AlignmentType.CENTER, AlignmentType.CENTER, AlignmentType.LEFT]));
B.push(note("映射表为系统配置项而非固定常量：可按所使用 OCR 引擎在目标图像分布上的错误统计进行校准（例如统计引擎将 0 误读为 O 的频次调整映射方向与覆盖集合），亦可为不同 OCR 引擎维护多套映射表并在运行时按引擎型号选择。此一般化表述应写入权利要求，避免将保护范围限定为具体字符集合。"));
B.push(pBold("S304（等长映射不变量与位置回映射）：三个空间满足两条不变量：其一，compact_text 由 text 仅做删除操作得到，故 compact_to_doc 单调不减，任意紧凑偏移区间可回查为原文偏移区间；其二，混淆映射为单字符到单字符（1:1）且不删除字符，故 confused_text 与 compact_text 严格等长，二者的字符偏移一一对应。由此，混淆空间与紧凑空间可以共用同一个回映射数组 compact_to_doc，无需为混淆空间单独维护映射结构。命中区间的回映射公式为："));
B.push(...pc([
  "设某空间中正则命中为左闭右开区间 [s, e)，",
  "若为原文空间：  文档区间 D = [s, e)",
  "若为紧凑/混淆空间： D = [ compact_to_doc[s], compact_to_doc[e-1] + 1 )",
  "随后由 D 经 CharMap 反查（5.1 的 span_to_block_ids）得到文本框集合。",
]));
B.push(pBold("S305（空间启停条件）：紧凑空间仅当 compact_text 不等于 text（即存在被删空白）时执行匹配；混淆空间仅当 confused_text 不等于 compact_text（即存在被映射字符）且当前规则绑定有校验器时执行匹配。两个条件避免无谓的重复检索，也使纯字母数字完好的文本完全不受归一化影响。"));
B.push(p("图 3 以「l38 OOl3 8000」为例完整展示了三空间的对齐关系与回映射路径：混淆空间命中区间 [0,11)，经 compact_to_doc 回查为文档区间 [0,13)，再经 CharMap 反查得到三个文本框全部纳入遮挡。"));
B.push(...figure("fig3_spaces_mapping.png", "图 3  三个匹配空间的对齐与等长字符映射回映射", 560));
B.push(h3("5.2.1 扩展实施例与泛化"));
B.push(p("（1）逆向混淆空间：对称地构造数字到字母的逆向映射（0 映射为 O、1 映射为 l 等），服务于字母为主的密钥类规则（API Key、Token 等被 OCR 将字母误读为数字的情形），其回映射机制与上述完全一致，仅映射表方向不同。"));
B.push(p("（2）置信度加权的空间选择：利用 OCR 文本框自带的识别置信度，对平均置信度低于阈值的文本框区域自动启用混淆空间（甚至扩大映射表覆盖），对高置信度区域仅启用原文与紧凑空间，在召回与开销之间自适应平衡。"));
B.push(p("（3）多套映射表并存：按 OCR 引擎型号、语言或版式维护多套混淆映射表，运行时按引擎元信息选择；映射表可通过配置文件或管理接口热更新。"));
B.push(p("（4）空间数量不限于三：凡满足「由原文空间经可回查的字符级变换派生、且变换保持可回映射性（删除型配单调数组、等长型直接复用数组）」的文本空间，均在本发明的匹配空间框架之内，例如去除标点空间、大小写折叠空间等。"));
B.push(h3("5.2.2 多重派生空间与回映射的边界安全"));
B.push(p("（1）多重混淆映射表并行派生：框架支持同时加载 K 张混淆映射表（例如按 OCR 引擎型号、按字体域各一张），各自作用于紧凑空间得到 K 个等长派生空间。由于每张表均为 1:1 等长映射，K 个派生空间共享同一个 compact_to_doc 回映射数组，无需 K 份映射结构；K 个空间按预设置信序统一参与 5.4 的先占去重。该实施例将「混淆归一化空间」从单一实例泛化为「等长派生空间族」，显著扩大保护范围。"));
B.push(p("（2）区间端点的边界安全：回映射公式采用 compact_to_doc[e-1] 加 1 的形式，天然保证命中区间至少包含一个实际字符（空区间不可能出现）；区间端点若落在合成分隔符上，反查阶段跳过合成记录、仅返回相邻实际文本框，不会把相邻敏感值的框错误并入。两条性质共同保证任意空间、任意命中形态下回映射的确定性。"));
B.push(p("（3）检索成本分析：三个（或 K 加二个）空间的正则检索共享同一份编译缓存，每个空间执行一次线性扫描，总复杂度与各空间长度之和成线性关系；由于紧凑与混淆空间不含空白，其实际长度不大于原文空间，整体开销与单空间多规则检索同数量级，不随空间数量增加产生超线性增长。"));

B.push(h2("5.3 利用校验规则对混淆匹配结果进行筛选（校验位门控）"));
B.push(p("本节解决的核心问题是：混淆归一化将大量非数字字符映射为数字，显著扩大了正则规则的命中面，必须以权威校验机制过滤误报；同时门控的施加位置必须精确——只作用于归一化空间，不改变原文与紧凑空间的既有召回行为。"));
B.push(h3("5.3.1 校验器定义"));
B.push(p("本发明将校验器实现为可插拔的纯函数注册表（表 3），规则与校验器通过规则元数据中的校验器名称绑定（例如身份证号规则绑定 china_id 校验器，银行卡号规则绑定 luhn 校验器，手机号规则绑定 cn_mobile 校验器）。"));
B.push(tcap("表 3  校验器注册表"));
B.push(tbl(["校验器名称", "适用敏感类型", "校验算法"],
  [["china_id", "中国居民身份证号（18 位）", "GB 11643 mod 11-2 加权校验位"],
   ["luhn", "银行卡号（15 至 19 位）", "Luhn 模 10 校验"],
   ["cn_mobile", "中国手机号（11 位）", "号段前缀与格式校验"],
   ["iban", "国际银行账号", "mod 97 校验"],
   ["vin", "车辆识别代号", "ISO 3779 加权校验"]],
  [22, 38, 40]));
B.push(h3("5.3.2 中国居民身份证号校验（GB 11643 mod 11-2）"));
B.push(p("18 位身份证号前 17 位为本体码 a1 至 a17，第 18 位为校验码。计算方法：S = (a1*W1 + a2*W2 + ... + a17*W17) mod 11，按余数查校验字符表「10X98765432」得到期望校验码，与实际第 18 位比对。权重与演算示例见表 4（以待校验串 11010519491231002X 为例，S = 167，167 mod 11 = 2，查表得期望校验码 X，与实际第 18 位一致，校验通过）。"));
B.push(tcap("表 4  身份证校验位演算示例（11010519491231002X）"));
B.push(tbl(["位序", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17"],
  [["本体码 a", "1", "1", "0", "1", "0", "5", "1", "9", "4", "9", "1", "2", "3", "1", "0", "0", "2"],
   ["权重 W", "7", "9", "10", "5", "8", "4", "2", "1", "6", "3", "7", "9", "10", "5", "8", "4", "2"],
   ["乘积", "7", "9", "0", "5", "0", "20", "2", "9", "24", "27", "7", "18", "30", "5", "0", "0", "4"]],
  [13, ...Array(17).fill(5.1)], [AlignmentType.CENTER, ...Array(17).fill(AlignmentType.CENTER)]));
B.push(p("乘积总和为 167，167 对 11 取模得余数 2，校验字符表第 2 位（从 0 计）为 X，与待校验串第 18 位一致，校验通过。若混淆归一化空间命中的 18 位串其校验位不符（例如串 110105194912310021），则判为归一化误报，直接丢弃。"));
B.push(h3("5.3.3 银行卡号校验（Luhn）"));
B.push(p("对 15 至 19 位数字串，从最右位起逐位编号 i = 0,1,2,...：i 为偶数的位取原值；i 为奇数的位乘 2，乘积大于 9 则减 9；将全部位求和，总和对 10 取模为 0 则校验通过。以 4111111111111111 为例：最左位 4 位于奇数编号位，4 乘 2 得 8；其余奇数编号位均为 1 乘 2 得 2（共 7 个，合计 14），偶数编号位合计 8，总和 30，30 mod 10 = 0，校验通过。"));
B.push(h3("5.3.4 手机号校验"));
B.push(p("去除可选的 +86 或 86 前缀后，要求剩余部分完整匹配 1[3-9] 后跟 9 位数字（即 11 位、第二位为 3 至 9）。该校验为格式与号段级校验，用于过滤归一化后碰巧凑成 11 位数字的非手机号内容。"));
B.push(h3("5.3.5 门控的施加位置与逻辑"));
B.push(p("门控逻辑严格限定为：仅当（a）当前匹配空间为混淆归一化空间，且（b）当前规则绑定有校验器时，对每个命中提取待校验值——优先取正则表达式第 1 捕获组（规则编写时将纯数值本体置于第 1 组，例如手机号规则将 +86 前缀置于组外），无捕获组则取命中整体——执行对应校验器，不通过则丢弃该命中。原文空间与紧凑空间的命中不做校验门控：此两空间中数字格式已被 OCR 正确识别，维持既有行为可保证默认输出的向后兼容与召回稳定。伪代码如下："));
B.push(...pc([
  "// 在 _append_matches 的候选处理流程中（紧随重叠判断之后）",
  "if space == \"confused\" and rule.validator != None:",
  "    value = match.group(1) if match.re.groups >= 1 else match.group(0)",
  "    check = VALIDATORS.get(rule.validator)      // 可插拔校验器注册表",
  "    if check is None or not check(value):",
  "        continue                                // 校验不通过：丢弃该候选（拦截误报）",
]));
B.push(note("与 CN113128504A 的本质区别（规避设计要点）：该先有技术以「检错到的不合规字符为对象做替换并复核」实现识别纠错；本发明的门控是「在完整派生匹配空间上检索、以校验器对候选做接受或丢弃的二值筛选」，不含任何字符替换纠错动作，且通过者不输出纠正文本而是回映射至图像坐标执行遮挡。撰写权利要求时应避免「替换错误字符」「纠错」等表述，强调「匹配空间构造 + 检索 + 校验筛选 + 位置回映射」的完整链路。"));
B.push(h3("5.3.6 门控失败的漏斗式移交"));
B.push(p("校验失败的候选并非简单消失，而是进入漏斗式移交路径：其文档区间被登记为「低置信敏感嫌疑区间」，首先移交字段标签邻接兜底复核（若区间邻近存在语义匹配的字段标签，按兜底遮挡）；其次移交像素带补偿兜底（若区间落入未识别文本带，按带遮挡）；若两级兜底均不覆盖，则按部署策略二选一：保守策略下将该区间按「疑似数字串」类别整体遮挡（宁过度不漏放），宽松策略下放行并计入审计日志供人工复核。该设计使校验门控在拦截误报的同时不产生新的漏检敞口，形成「校验拦截与兜底回收」的闭环。"));
B.push(p("此外，校验器所依赖的数据可热更新：手机号校验的号段库、校验器注册表本身均可经配置或管理接口在线更新，无需重启服务，适应号段扩容与新增敏感类型（如新增 IBAN 场景）的演进需求。"));

B.push(h2("5.4 不同匹配空间结果的重叠判断、优先级判断及去重"));
B.push(p("本节解决的核心问题是：同一敏感值可能在多个空间同时命中（例如纯数字拆框值在紧凑空间与混淆空间的相同区间均能匹配），跨规则也可能对同一区间重复命中（例如 18 位数字同时满足身份证规则与税号规则的格式），必须建立确定性的消解机制，避免重复遮挡、重复计数与归因混乱。本发明采用两级优先级与先占式去重（S401 至 S407，流程见图 4）："));
B.push(pBold("S401（规则优先级遍历）：将全部已启用规则按其元数据优先级 priority 降序排序后遍历，高优先级规则的命中先行占据文档区间。规则优先级由规则语义确定（如身份证规则高于泛化的长数字串规则），也可由管理员调整。"));
B.push(pBold("S402（空间置信顺序遍历）：对每条规则，依置信级从高到低依次在原文空间、紧凑空间、混淆归一化空间执行检索。空间置信顺序的依据是：原文空间未经任何变换、紧凑空间仅删除空白、归一化空间做了字符替换，变换强度递增则误报风险递增。"));
B.push(pBold("S403（候选生成与回映射）：在当前空间以正则检索得到候选命中区间 [s, e)；按 5.2 的回映射公式换算为文档区间 D（原文空间直接使用，其余空间经 compact_to_doc 回查）。"));
B.push(pBold("S404（区间重叠判断）：对已记录的全部命中区间集合 M，若存在任一 m 属于 M 使得「D 与 m 相交」，则当前候选被判定为重复，直接丢弃。两个左闭右开区间 [a1,b1) 与 [a2,b2) 相交当且仅当 not (b1 小于等于 a2 或 a1 大于等于 b2)。先占原则保证了高置信空间与高优先级规则的命中被保留，后到的低置信命中即使覆盖同一区域也不再计入，天然实现「原文优于紧凑、紧凑优于归一化、高优先级规则优于低优先级规则」的消解顺序。"));
B.push(pBold("S405（校验位门控）：见 5.3.5，仅作用于归一化空间的候选。"));
B.push(pBold("S406（文本框可映射性判断）：文档区间 D 经 span_to_block_ids 反查；若结果为空（例如命中完全落在合成分隔符上），丢弃该候选。"));
B.push(pBold("S407（命中记录与归因）：记录命中条目，至少包含：规则标识、规则名称、占位符、文档区间 D、文本框集合 block_ids、以及归因字段 matched_via（取值为命中所处的空间标识 text 或 compact 或 confused，命名实体识别补充命中记为 ner）。归因字段用于命中来源审计与统计（例如服务接口返回各空间命中计数），同时是实现「先占去重」的可观测证明。全部规则遍历完成后，命中列表按（文档区间起点升序、区间长度降序）排序输出，供后续遮挡区域生成按阅读顺序处理。"));
B.push(...figure("fig4_match_gate_dedup.png", "图 4  匹配、门控与跨空间去重流程（S401 至 S407）", 520));
B.push(p("主流程伪代码（与图 4 一一对应）："));
B.push(...pc([
  "function match_rebuilt_text(rebuilt, rule_ids):",
  "    rules = enabled_rules() 按优先级 priority 降序          // S401",
  "    matches = []",
  "    for rule in rules:",
  "        if rule_ids 非空 且 rule.id 不在其中: continue",
  "        append_matches(matches, rule, rebuilt.text,   space=\"text\")     // S402",
  "        if rebuilt.compact_text != rebuilt.text:",
  "            append_matches(matches, rule, rebuilt.compact_text, space=\"compact\")",
  "        if rule.validator 且 rebuilt.confused_text != rebuilt.compact_text:",
  "            append_matches(matches, rule, rebuilt.confused_text,",
  "                           space=\"confused\", validator=rule.validator)  // 门控见 5.3.5",
  "    return sort(matches, key=(doc_start 升序, 长度降序))                // S407",
  "",
  "function append_matches(matches, rule, text, space, validator=None):",
  "    for m in rule.compiled.finditer(text):",
  "        D = (m 区间) 若 space==\"text\"，否则 [ctd[m.start], ctd[m.end-1]+1)   // S403",
  "        if 与 matches 中任一已有区间相交: continue                        // S404 先占去重",
  "        if validator 且 space==\"confused\" 且 校验不通过(m): continue       // S405",
  "        block_ids = span_to_block_ids(rebuilt, D)                        // S406",
  "        if block_ids 为空: continue",
  "        matches.append(命中(rule, D, block_ids, matched_via=space))      // S407",
]));
B.push(tcap("表 5  空间优先级与门控规则汇总"));
B.push(tbl(["匹配空间", "置信级", "启用条件", "校验位门控", "归因取值"],
  [["原文空间 text", "高", "恒启用", "否", "text"],
   ["紧凑空间 compact", "中", "存在被删除空白", "否", "compact"],
   ["混淆归一化空间 confused", "低", "存在被映射字符且规则绑定校验器", "是", "confused"],
   ["命名实体识别补充", "独立通道", "调用方显式开启", "否", "ner"]],
  [26, 12, 34, 14, 14]));
B.push(p("数值说明：对纯数字拆框值「138 0013 8000」，紧凑空间命中区间回映射后与混淆空间的相同命中区间完全重叠，按先占原则仅保留紧凑空间命中（matched_via = compact），不重复计数；对形近受损值「l38 OOl3 8000」，紧凑空间无法命中，混淆空间命中成为唯一有效命中（matched_via = confused），漏检被消除。两例合并表明去重机制在消除冗余的同时不损失召回。"));
B.push(h3("5.4.1 扩展实施例：标签上下文动态优先级与跨通道交叉校验"));
B.push(p("（1）标签上下文动态优先级：规则优先级除静态元数据外叠加上下文因子参与 S401 排序。当候选命中的文档区间邻近（同行左侧或右侧预设距离内）存在与该规则语义对应的字段标签时（例如身份证规则候选邻近「公民身份号码」标签），将该规则的等效优先级提升一级；当候选处于与规则语义明显不符的标签上下文时（例如 18 位数字串紧邻「订单号」标签），降低其等效优先级。该机制使同一规则在不同版式中按上下文获得不同的消解顺序，减少长数字串的类别错配误遮。"));
B.push(p("（2）命名实体识别与规则通道的交叉校验：对命名实体识别给出的实体区间与规则命中的数字类区间执行重叠检测。当某实体文本形态同时满足某数字规则格式而该校验（如 Luhn 或 GB 11643）不通过时，按命名实体通道保留命中并归因 ner，不再按数字规则遮挡；两通道对同一区间均成立时以先占规则消解并记录双通道归因。此机制消解人名拼音串等文本恰巧构成数字串形态的低概率歧义。"));
B.push(h3("5.4.2 去重判定的数据结构与置信评分泛化"));
B.push(p("（1）有序区间表与对数级重叠判定：基础实施例中重叠判定对已有命中线性扫描；强化实施例将已接受命中维护为按文档区间起点有序的区间表，新候选经二分定位仅与相邻区间比较，单候选判定降为对数级，规则与候选规模增大时去重环节不成为瓶颈。两档实施例的判定语义完全一致（任意相交即判重），仅数据结构不同。"));
B.push(p("（2）优先级的两种实施形态：字典序形态即规则优先级降序加空间置信顺序的两级比较（前述 S401 与 S402）；连续评分形态将三者加权为单一评分，空间置信权重（原文最高）、规则优先级权重与候选所覆盖文本框的平均识别置信度（OCR 引擎输出的置信度）线性加权求和，按评分降序执行先占。连续评分形态将去重顺序与 OCR 质量联动：同一值在高置信块上的命中优先于低置信块上的命中。"));
B.push(p("（3）抑制计数与归因审计：被先占去重丢弃的候选不丢弃其统计价值，按其原属空间计入抑制计数；响应元数据同时给出各空间的接受计数与抑制计数，运营侧可据此监控归一化空间的实际增益与冗余度，并反哺映射表与校验器的调参。"));

B.push(h2("5.5 遮挡区域生成：顶点外扩凸包精确遮挡"));
B.push(p("命中映射得到文本框集合后，遮挡区域按如下步骤生成（S501 至 S504，几何示意见图 5）：S501 将命中的文本框集合按行分组（同一命中的跨行片段分别处理）；S502 对组内每个文本框的实际四边形，将其每个顶点沿「顶点指向多边形质心」的反方向外扩固定像素（实施例取 3 像素，可配置）；S503 对外扩后的全部顶点求凸包（实施例采用 Andrew 单调链算法，时间复杂度 O(n log n)）；S504 以凸包多边形作为遮挡区域执行填充绘制，凸包的轴对齐外接框仅用于坐标上报、去重键与账本裁剪，不参与绘制。"));
B.push(p("对水平文本，各四边形外扩后的凸包即退化为外接矩形，遮挡行为与现有轴对齐方案完全一致（向后兼容）；对倾斜或轻透视文本，凸包贴合文本实际轮廓，遮挡面积显著小于外接矩形（实施例单测断言凸包面积小于外接框面积的百分之九十五），相邻内容过度遮挡问题被消除。顶点共线等退化情形回退为外接矩形遮挡。"));
B.push(...figure("fig5_hull_masking.png", "图 5  轴对齐外接矩形（左）与顶点外扩凸包（右）遮挡对比", 580));

B.push(h2("5.6 多级兜底遮挡"));
B.push(h3("5.6.1 字段标签邻接兜底"));
B.push(p("针对 OCR 将数字拆断、空格化或部分漏识别导致正则无法完整命中的情形（版式语义层兜底）：维护敏感字段标签正则表（公民身份号码、身份证号、手机、电话、邮箱、住址、银行卡、纳税人识别号、统一社会信用代码、发票代码、发票号码、订单号、运单号、快递单号等）；对命中标签的文本框，在其所在行内寻找右侧邻近（左边缘不小于标签右边缘减去 max(3px, 行高乘 0.25)）且文本形态符合字段值特征（含 3 位以上连续数字、或邮箱形态、或 7 位以上字母数字混合、或 2 个以上汉字）的文本框组，将整组纳入遮挡；若同行无可识别值块，则按标签框宽度的 2.4 倍（下限 120 像素）遮挡其右侧带状区域。标签本身即是强信号，此兜底不依赖数字完整可读。"));
B.push(h3("5.6.2 像素带补偿兜底"));
B.push(p("针对 OCR 整行漏检（如长 API Key、Token 等英文符号混合串）导致敏感像素被原样返回的风险（失效安全侧兜底）：将图像灰度化；逐行统计灰度小于阈值（实施例取 150）的暗像素数，超过行阈值 max(8, 图像宽度乘 0.003) 的行记为活动行；将垂直间隔不超过 3 像素的活动行合并为文本带；丢弃高度小于 8 像素或大于 max(120, 图高四分之一) 的带；与任何已检出 OCR 文本框纵向重叠率达到百分之四十五的带视为已被识别覆盖而剔除；剩余带中若暗像素的水平跨度达到 max(240px, 图宽的百分之二十八)，则对该带整体执行遮挡。该兜底宁可过度遮挡也不放行未识别的长文本像素。"));
B.push(h3("5.6.3 分辨率自适应二次识别兜底"));
B.push(p("针对长边受限缩放导致小字号文本在低分辨率下漏检或误读的情形（第三级兜底）：S531 将两类区域登记为待复核区域——经 5.6.2 判定为疑似文本带但被宽度判据剔除的窄带，以及识别置信度低于阈值的低置信文本块外接邻域；S532 在原图坐标系上按外接框加边距裁剪待复核区域，并放大至目标识别分辨率（实施例为放大至区域短边不低于 640 像素）；S533 对裁剪放大后的子图单独执行 OCR，所得文本框坐标按裁剪偏移与放大系数逆变换回原图坐标系；S534 将二次识别得到的文本框并入全局文本框集合，重新执行行重建、三空间匹配、校验门控与去重遮挡全流程。二次识别仅针对少量可疑区域局部执行，整体计算量增加可控，同时显著恢复小字号与低对比度场景的召回。"));

B.push(h2("5.7 文档类型自适应策略级联"));
B.push(p("针对不同版式误遮特性不同的问题（可选旁路，调用方以开关启用）：S521 基于 OCR 文本框信号做轻量类型判定——对每个文本框的紧凑文本匹配四类场景信号正则（身份证件、发票票据、物流面单、配置截图，信号词例如「增值税、价税合计、统一社会信用代码」「收货、寄件、运单、快递」「公民身份号码、签发机关、有效期限」「api_key、token、secret、https 冒号双斜杠、点 env、localhost、IPv4 形态」），统计各场景信号文本框数；S522 判据为最高计数不小于 2 且严格大于次高计数，满足则判定为该场景，否则回退通用场景（判据保守设计保证不漏遮）；S523 按场景策略表（表 6）级联调整规则类别子集与两级兜底开关；S524 执行策略并将判定结果与所用策略写入响应元数据。整个判定仅依赖已有 OCR 文本，不引入任何额外模型推理，适配边缘弱性能设备。"));
B.push(tcap("表 6  场景策略表（实施例）"));
B.push(tbl(["场景类型", "规则类别子集", "字段标签兜底", "像素带兜底", "NER 提示"],
  [["身份证件", "全量", "开", "开", "开"],
   ["发票 / 票据", "全量", "开", "开", "关"],
   ["物流面单", "全量", "开", "开", "开"],
   ["配置截图", "api_key 与 pii 类", "关", "开", "关"],
   ["通用（回退）", "全量", "开", "开", "开"]],
  [22, 26, 18, 17, 17]));
B.push(...figure("fig6_adaptive_cascade.png", "图 6  文档类型自适应策略级联", 560));

B.push(h2("5.8 可选扩展：可逆脱敏账本（独立发明构思）"));
B.push(p("本节机制与上述识别遮挡链路相互独立，属另一发明构思，建议单独申请，此处仅作整体方案的完备性描述（图 7）：调用方以可逆开关发起请求并提供 32 字节密钥（或由部署环境变量提供密钥引用）；服务在遮挡绘制之前，对每个遮挡区域裁剪原始像素块并做 PNG 无损序列化；以 AES-256-GCM 逐区域加密，每区域使用独立随机 nonce，并以区域序号作为附加认证数据（AAD）防止账本条目被调换；加密后的条目集合（区域序号、外接框、nonce、密文）构成与脱敏图像配对返回的加密账本；还原接口接收脱敏图、账本与密钥，逐区域解密并贴回像素（裁剪框含 1 像素边缘余量以完整覆盖多边形填充的边界像素语义），实现像素级无损还原，单区域解密失败仅记录于报告而不中断其余区域。账本不含明文，无密钥方无法还原。"));
B.push(...figure("fig7_reversible_ledger.png", "图 7  可逆脱敏账本的脱敏与还原时序", 560));

B.push(h2("5.9 系统实施例"));
B.push(p("与方法对应的系统实施例按模块划分如表 7。各模块可部署于同一计算设备（实施例为容器化的服务进程，运行于 ARM 边缘设备），亦可分布式部署；OCR 模型与命名实体识别模型经统一模型仓库按需拉取，识别与遮挡链路不依赖云端服务。"));
B.push(tcap("表 7  系统模块划分"));
B.push(tbl(["模块", "职责", "对应章节"],
  [["图像接入模块", "图像解码、预处理缩放、坐标逆变换", "S101 至 S103"],
   ["行重建模块", "行聚类、行内排序、NFKC 归一化、CharMap 构建", "5.1"],
   ["匹配空间构造模块", "紧凑空间、混淆归一化空间及回映射数组构造", "5.2"],
   ["规则与校验器注册模块", "规则元数据（含校验器绑定）管理、正则编译缓存、校验器注册表", "5.3"],
   ["匹配与去重模块", "三空间检索、区间回映射、重叠判断、先占去重、归因记录", "5.4"],
   ["遮挡区域生成模块", "顶点外扩凸包、行分组遮挡区域计算", "5.5"],
   ["多级兜底模块", "字段标签邻接兜底、像素带补偿兜底", "5.6"],
   ["场景策略模块", "文档类型判定与策略级联（可选）", "5.7"],
   ["遮挡渲染与账本模块", "多边形填充绘制、可逆账本生成与还原（可选）", "5.8"]],
  [24, 52, 24]));

/* 六、有益效果 */
B.push(h1("六、有益效果"));
B.push(p("（1）碎片化漏检消除：任意被 OCR 拆框、块间引入空格换行的敏感值，经紧凑空间检索均可命中，并精确定位回全部来源文本框；实施例中三框拆分手机号稳定命中。"));
B.push(p("（2）形近误读漏检消除：数字被误读为形近字母的敏感值（如 l38 OOl3 8000 形态的手机号）经混淆归一化空间检索命中；该类漏检在现有云服务与开源框架中均无检索手段。"));
B.push(p("（3）误报受控且无漏检敞口：校验位门控使归一化空间的命中必须通过 GB 11643、Luhn 或号段校验；实施例中末位校验码不符的 18 位串被稳定拦截，不产生误遮；被拦截候选经 5.3.6 漏斗式移交由两级兜底复核，门控不引入新的漏检敞口。"));
B.push(p("（4）无重复计数与可审计：先占式跨空间去重保证同一敏感值单一命中并携带空间归因，响应元数据可给出各空间命中计数，便于运营监控归一化空间的实际贡献。"));
B.push(p("（5）遮挡精确度提升：倾斜文本的凸包遮挡面积显著小于轴对齐外接矩形（实施例断言小于外接框面积百分之九十五），相邻内容误遮减少；水平文本行为不变。"));
B.push(p("（6）失效安全：像素带补偿兜底保证 OCR 整行漏检的长密钥串不会被原样返回；字段标签邻接兜底覆盖数字拆断场景。"));
B.push(p("（7）边缘设备可行：全链路无额外模型推理（场景判定基于既有 OCR 文本信号），在 Jetson 级 ARM 边缘设备的实测基准中，六类复杂版式图片规则平均命中 8.83 项每图，叠加命名实体识别后 13.83 项每图（增益约百分之五十六点六），四并发下 P95 约 3 秒，持续压力测试零失败，验证了机制的工程可行性。"));
B.push(p("（8）可逆能力（可选）：授权持钥方可对已脱敏图像做像素级无损还原，满足审计与纠错场景，且账本不含明文、无密钥方无法还原。"));
B.push(p("（9）小字号与低对比度召回恢复：分辨率自适应二次识别兜底以可控的局部开销，对疑似漏检区域放大重识别并并回主流程，恢复长边受限缩放场景下的召回损失，与前两级兜底共同构成覆盖「可读性受损、版式断裂、整体漏检」三类失败形态的三级兜底体系。"));

/* 七、附图说明 */
B.push(h1("七、附图说明"));
B.push(tcap("表 8  附图清单"));
B.push(tbl(["图号", "名称", "核心内容"],
  [["图 1", "总体处理流程与模块关系", "S101 至 S110 十阶段流程及两个可选旁路"],
   ["图 2", "行重建与字符映射表构建", "文本框、重建文本、合成分隔符与 CharMap 记录"],
   ["图 3", "三空间对齐与等长字符映射回映射", "原文、紧凑、混淆三空间字符网格、compact_to_doc 数组与回映射路径"],
   ["图 4", "匹配、门控与跨空间去重流程", "S401 至 S407 判定流程（含菱形判定分支）"],
   ["图 5", "顶点外扩凸包遮挡几何", "外接矩形与凸包遮挡的面积对比及构造步骤"],
   ["图 6", "文档类型自适应策略级联", "信号统计、判据与场景策略表"],
   ["图 7", "可逆脱敏账本时序", "脱敏建账与授权还原的交互时序（独立构思）"]],
  [10, 34, 56]));

/* 八、具体实施方式 */
B.push(h1("八、具体实施方式"));
B.push(h2("8.1 实施例一：形近误读且拆框的手机号端到端演算"));
B.push(p("输入图像经 OCR 输出同一行三个文本框：B0 文本 l38、B1 文本 OOl3、B2 文本 8000（数字 1 被误读为 l，两个 0 被误读为 O）。端到端处理过程逐步演算如表 9。"));
B.push(tcap("表 9  实施例一逐步演算"));
B.push(tbl(["步骤", "空间 / 机制", "过程与结果"],
  [["1", "行重建（5.1）", "重建文本 text = l38 空格 OOl3 空格 8000（13 字符），偏移 3、8 为合成分隔符；CharMap 登记 5 条记录"],
   ["2", "原文空间（5.2）", "手机号正则要求连续 11 位数字，text 中存在字母与空格，不命中"],
   ["3", "紧凑空间（5.2）", "compact_text = l38OOl38000（11 字符），仍含字母，不命中；compact_to_doc = [0,1,2,4,5,6,7,9,10,11,12]"],
   ["4", "混淆空间（5.2）", "逐字符映射后 confused_text = 13800138000，手机号正则命中区间 [0, 11)，第 1 捕获组为 13800138000"],
   ["5", "校验门控（5.3）", "cn_mobile 校验：去除可选前缀后完整匹配 1[3-9] 加 9 位数字，通过"],
   ["6", "回映射（5.2）", "文档区间 D = [ctd[0], ctd[10]+1) = [0, 13)"],
   ["7", "反查（5.1）", "D 与 CharMap 全部非合成记录相交，block_ids = {0, 1, 2}"],
   ["8", "遮挡（5.5）", "B0、B1、B2 外扩凸包区域整体遮挡，matched_via = confused，命中计数归因至归一化空间"]],
  [8, 22, 70]));
B.push(h2("8.2 实施例二：校验位拦截归一化误报"));
B.push(p("输入文本框内容 llO10519491231002l（末位校验码 X 被误读为 l）。原文与紧凑空间均无法命中身份证规则（含字母）；混淆空间映射后为 110105194912310021，格式满足 18 位身份证正则并进入校验门控；按表 4 算法，该本体码的期望校验码为 X 而实际末位为 1，校验不通过，候选被丢弃。该值不被误遮，验证了门控对归一化误报的拦截能力（若该值真实存在，其像素仍受字段标签邻接兜底与像素带兜底保护）。"));
B.push(h2("8.3 实施例三：倾斜物流面单的凸包遮挡"));
B.push(p("物流面单照片中收件人手机号两个文本框分别带有约 5 度倾斜。现有轴对齐方案对外接框 union 涂黑，覆盖了上一行的地址文字；本发明对两框四边形顶点外扩 3 像素后取凸包，遮挡区域为贴合倾斜轮廓的六边形，实测面积约为外接框的八成，相邻行内容不再被覆盖；对同一面单的水平文本（寄件人信息），凸包退化为矩形，输出与现有方案一致。"));
B.push(h2("8.4 实施例四：配置截图的自适应级联"));
B.push(p("配置截图包含 api_key 赋值行、token 赋值行与 URL 各一块。场景判定模块统计信号：配置截图类 3 个信号框，其余场景 0 个，满足最高计数不小于 2 且严格领先，判定为配置截图；策略级联将规则集收窄为 api_key 与 pii 类（单据类规则被过滤，长字母数字串不再被发票号、运单号规则泛化误遮），并关闭字段标签邻接兜底（中文标签信号在该版式下无意义），像素带兜底保持开启。实测该配置截图的误遮条目归零，而密钥、手机号、IP 命中不受影响。"));

/* 九、关键点及欲保护点 */
B.push(h1("九、关键点及欲保护点（权利要求建议）"));
B.push(h2("9.1 独立权利要求建议（方法）"));
B.push(p("一种图像敏感信息识别与遮挡方法，其特征在于包括以下步骤，各特征为完成整体发明构思不可分割的技术特征（建议全部写入独立权利要求，代理可视检索结果微调）："));
B.push(p("（1）对图像执行 OCR 得到含文本与坐标的文本框集合，将文本框按行聚类、行内排序并拼接为重建文本，在拼接过程中逐字符区间登记字符映射表，所述字符映射表记录字符区间与来源文本框编号的对应关系及是否为合成分隔符（对应 5.1）；"));
B.push(p("（2）由所述重建文本派生至少一个匹配空间，包括删除空白字符的紧凑空间、以及对所述紧凑空间逐字符应用形近字符映射得到的等长的混淆归一化空间，并维护由派生空间字符偏移回查重建文本偏移的回映射数组（对应 5.2）；"));
B.push(p("（3）在所述匹配空间中分别执行敏感信息规则检索，命中区间经所述回映射数组与所述字符映射表换算为重建文本区间并进一步映射为文本框集合（对应 5.2 与 5.1）；"));
B.push(p("（4）对所述混淆归一化空间中的命中，按命中敏感值类型绑定的校验规则执行校验位验证，未通过者被丢弃（对应 5.3）；"));
B.push(p("（5）对不同匹配空间与不同规则产生的命中区间执行重叠判断，按规则优先级与空间置信顺序以先占方式去重并记录命中所处空间的归因（对应 5.4）；"));
B.push(p("（6）依据去重后命中的文本框集合生成遮挡区域并绘制，输出脱敏图像（对应 5.5）。"));
B.push(h2("9.2 从属权利要求建议"));
B.push(p("（1）行聚类的自适应阈值判据（max(8, 0.65 倍当前框高, 行内均值) 与垂直中心距离比较）；（2）NFKC 归一化与合成分隔符（空格与换行）的插入时机；（3）混淆字符映射表为可配置项、按 OCR 引擎错误统计校准或多套并存按引擎选择；（4）回映射公式（compact_to_doc[s], compact_to_doc[e-1]+1）；（5）校验器注册表机制及具体校验器（GB 11643 mod 11-2、Luhn、手机号段、IBAN mod 97、VIN）；（6）门控仅施加于归一化空间且捕获组优先取第 1 组；（7）命中排序键（起点升序、长度降序）与归因字段；（8）顶点沿质心反向外扩加凸包的遮挡区域构造及退化回退；（9）字段标签邻接兜底的邻近判据与值形态判据；（10）像素带补偿兜底的行阈值、带合并间隔、重叠率剔除与宽度判据；（11）文档类型判据（最高计数不小于 2 且严格领先，否则回退）与场景策略级联；（12）逆向混淆空间与置信度加权空间选择；（13）标签上下文动态优先级（语义标签邻近提升、相异标签邻近降低）；（14）命名实体识别与规则通道的交叉校验与双通道归因；（15）分辨率自适应二次识别兜底（待复核区域登记、局部裁剪放大、坐标逆变换、并集重跑主流程）；（16）码点级偏移与块级倒排索引（文本框到文档区间直达检索）；（17）门控失败的漏斗式移交（嫌疑区间经两级兜底复核与保守或宽松策略）；（18）有序区间表二分重叠判定、多因子连续置信评分排序与抑制计数审计；（19）可逆脱敏账本（建议移入独立申请）。"));

/* 十、与先有技术的区别 */
B.push(h1("十、与先有技术的区别及规避设计"));
B.push(h2("10.1 先有技术对照"));
B.push(tcap("表 10  先有技术对照与本发明差异"));
B.push(tbl(["先有技术", "其披露内容", "本发明差异（特征级）"],
  [["CN113128504A（校验规则纠错）", "形近替换字符集对检出的不合规字符做替换，校验位复核，输出纠错后识别文本（证件机读码场景）", "目的为脱敏遮挡而非纠错输出；无字符替换动作，而是构造完整派生匹配空间做检索；命中经等长映射与字符映射表回定位至图像坐标；多空间置信顺序先占去重与归因为其所未见"],
   ["云服务图像隐去 / 开源图像脱敏组件", "OCR 后按检测器（部分含校验和）识别并在文本框涂矩形", "无混淆归一化匹配空间（形近误读直接漏检）；无跨空间去重归因；矩形遮挡对倾斜文本过度覆盖"],
   ["midecal_tool（开源）", "以 OCR 文本行四点框生成跟随倾斜的遮挡", "本发明为命中文本框组的组级区域构造（多框顶点外扩后取凸包），非单行四点直接填充；且与三空间匹配机制联动"],
   ["CVPR 2018 隐私遮挡论文", "文本区域凸包经 DenseCRF 细化用于遮挡", "凸包作用于分割掩码并需额外概率图推断；本发明为四边形顶点外扩的确定性几何构造，无额外模型"],
   ["US20240202865A1（可逆图像混淆）", "密钥可逆像素变换加访问配置（含 sidecar 元数据）授权可见", "本发明账本为遮挡前裁剪像素块的独立 AES-256-GCM 加密条目集（独立 nonce 与区域序号 AAD），配还原接口解密贴回，非原图内像素变换（该机制建议独立申请）"],
   ["CN119743558A（可恢复图像脱敏）", "区域像素一次一密异或，参数经 LSB 嵌入脱敏图自身", "本发明账本与图像分离传输，非隐写嵌入；采用 AEAD 认证加密与逐区域独立 nonce（该机制建议独立申请）"]],
  [20, 36, 44]));
B.push(h2("10.2 针对 CN113128504A 的重点规避（最强先有技术）"));
B.push(p("撰写时应当：（1）全文避免「替换」「纠错」「检错」等先有技术核心表述，统一使用「派生匹配空间」「检索」「校验筛选」「丢弃候选」；（2）独立权利要求必须包含位置回映射特征（回映射数组加字符映射表到文本框集合）与遮挡执行步骤——该特征使方案整体脱离字符串层纠错的范畴；（3）保留跨空间置信顺序去重与归因特征作为创造性论证支点；（4）从属权利要求以门控仅施加于归一化空间、捕获组优先、校验器注册表可插拔等实施细节收窄。"));
B.push(h2("10.3 查新状态说明"));
B.push(p("截至撰写日已完成的初查（详见配套文件 docs/patent-prior-art-notes.md）未发现覆盖本发明整体组合的单篇先有技术；机制层面新颖性评级：匹配空间与门控组合为中等，场景级联为中等（相对最安全），凸包遮挡为中低（仅作从属特征），可逆账本为低至中（建议独立申请并预期引用 US20240202865A1 答辩）。正式提交前应由代理机构出具查新报告。"));

/* 十一、术语表 */
B.push(h1("十一、术语表"));
B.push(tcap("表 11  术语与缩写"));
B.push(tbl(["术语", "释义"],
  [["文本框（block）", "OCR 输出的最小识别单元，含文本串、四边形顶点、外接框与置信度"],
   ["重建文本（text）", "按行序与行内序拼接、插入合成分隔符后的文档文本"],
   ["紧凑空间（compact）", "删除重建文本全部空白得到的匹配空间"],
   ["混淆归一化空间（confused）", "对紧凑空间逐字符应用形近映射得到的等长匹配空间"],
   ["compact_to_doc", "紧凑（或混淆）偏移到原文偏移的回映射数组"],
   ["CharMap", "字符区间与文本框编号及合成标记的映射记录集合"],
   ["先占去重", "高置信（规则优先级与空间置信序）命中先行占据区间，后续重叠候选丢弃"],
   ["matched_via", "命中归因字段，标识命中产生的匹配空间或通道"],
   ["校验位门控", "对归一化空间命中执行校验规则验证并丢弃未通过者的机制"],
   ["凸包遮挡", "文本框组四边形顶点外扩后取凸包作为遮挡区域的构造方式"],
   ["二次识别", "对疑似漏检区域裁剪放大后局部重跑 OCR，坐标逆变换并并回主流程的兜底机制"],
   ["账本（ledger）", "遮挡区域原始像素的 AEAD 加密条目集合，用于授权还原"]],
  [26, 74]));

/* 十二、申请信息 */
B.push(h1("十二、申请信息与保密声明"));
B.push(p("发明人：胡建星；申请人：（提交时填写）；联系人：胡建星，联系方式：【请填写】；本交底书所涉实施例代码位于内部仓库 apps/desensitize 目录，测试与基准数据位于 docs/image-deep-benchmark-20260812 目录。"));
B.push(p("保密声明：本交底书含未公开的技术方案细节，属内部保密文件，仅限专利申请流程相关人员查阅，不得对外传播。正式申请前请勿公开发布实施例代码、基准报告或本文件内容，以免构成自有技术公开。"));
const lastNote = new Paragraph({
  alignment: AlignmentType.JUSTIFIED,
  indent: { firstLine: 480 },
  spacing: { line: 312, before: 200 },
  children: [new TextRun({ text: "（正文完）", size: 24, color: P.secondary, font: { ascii: "Times New Roman", eastAsia: "SimSun" } })],
});
B.push(lastNote);

/* ════════════════════ 文档组装 ════════════════════ */
const pgSize = { width: 11906, height: 16838 };
const pgMargin = { top: 1440, bottom: 1440, left: 1701, right: 1417 };

const doc = new Document({
  creator: "ictrek",
  title: "专利技术交底书：基于多匹配空间与多级兜底的图像敏感信息识别与遮挡方法及系统",
  styles: {
    default: {
      document: {
        run: { font: { ascii: "Times New Roman", eastAsia: "SimSun" }, size: 24, color: "000000" },
        paragraph: { spacing: { line: 312 } },
      },
      heading1: {
        run: { font: { ascii: "Times New Roman", eastAsia: "SimHei" }, size: 32, bold: true, color: P.headPrimary },
        paragraph: { spacing: { before: 360, after: 160, line: 312 }, outlineLevel: 0 },
      },
      heading2: {
        run: { font: { ascii: "Times New Roman", eastAsia: "SimHei" }, size: 28, bold: true, color: P.headPrimary },
        paragraph: { spacing: { before: 260, after: 120, line: 312 }, outlineLevel: 1 },
      },
      heading3: {
        run: { font: { ascii: "Times New Roman", eastAsia: "SimHei" }, size: 24, bold: true, color: P.headPrimary },
        paragraph: { spacing: { before: 200, after: 100, line: 312 }, outlineLevel: 2 },
      },
    },
  },
  sections: [
    {
      properties: { page: { size: pgSize, margin: { top: 0, bottom: 0, left: 0, right: 0 } } },
      children: buildCoverR1({
        title: "基于多匹配空间与多级兜底的图像敏感信息识别与遮挡方法及系统",
        subtitle: "专 利 技 术 交 底 书",
        englishLabel: "PATENT DISCLOSURE",
        metaLines: [
          "文档编号：PJ-2026-001",
          "发明人：胡建星",
          "申请人：（提交时填写）",
          "撰写日期：2026 年 8 月 19 日",
          "密　　级：内部保密",
        ],
        footerLeft: "ictrek desensitize",
        footerRight: "2026-08",
        palette: P,
      }),
    },
    {
      properties: {
        type: SectionType.NEXT_PAGE,
        page: { size: pgSize, margin: pgMargin, pageNumbers: { start: 1, formatType: NumberFormat.UPPER_ROMAN } },
      },
      footers: { default: pageNumFooter() },
      children: [
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 480, after: 360 },
          children: [new TextRun({ text: "目　　录", bold: true, size: 32, font: { eastAsia: "SimHei", ascii: "Times New Roman" }, color: P.headPrimary })],
        }),
        new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" }),
        new Paragraph({
          spacing: { before: 200 },
          children: [new TextRun({
            text: "说明：本目录由域代码生成。编辑后请在目录上点击右键并选择「更新域」以刷新页码。",
            italics: true, size: 18, color: "888888", font: { ascii: "Times New Roman", eastAsia: "SimSun" },
          })],
        }),
      ],
    },
    {
      properties: {
        type: SectionType.NEXT_PAGE,
        page: { size: pgSize, margin: pgMargin, pageNumbers: { start: 1, formatType: NumberFormat.DECIMAL } },
      },
      headers: { default: docHeader() },
      footers: { default: pageNumFooter() },
      children: B,
    },
  ],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log("written:", OUT, buf.length, "bytes");
});
