# 四机制先有技术查新笔记（2026-08）

检索范围：Google Patents（CN/US/WO）、学术论文、开源项目与云产品文档；每个机制
4-8 组中英文检索词。专利号均来自实际检索结果页；**未命中方向已如实标注**。本笔记
为初查，正式申请前仍需代理机构查新报告。

## 机制二（混淆归一化 + 校验位门控）— 评级：中

最接近先有技术：

- [CN113128504A 基于校验规则的OCR识别结果纠错方法](https://patents.google.com/patent/CN113128504A/zh)：
  形近字符替换生成候选 + 校验规则（身份证/银行卡）匹配，用于**纠正识别结果输出
  正确文本**。单篇最接近，"混淆替换 + 校验位验证"核心逻辑已被披露。
- [Microsoft Presidio](https://microsoft.github.io/presidio/) /
  [presidio-image-redactor](https://pypi.org/project/presidio-image-redactor/)：
  正则 + Luhn 门控 + OCR 框涂黑整条链路已开源；但 OCR 混淆（O→0 等）导致 Luhn
  直接失败漏检，**无归一化匹配空间、无多空间去重**。
- [Google Cloud DLP 图像隐去](https://docs.cloud.google.com/sensitive-data-protection/docs/concepts/image-redaction)：
  OCR + 含 checksum 的 infoType 检测，同样无混淆归一化空间。
- 旁证：[US6205261B1](https://patents.google.com/patent/US6205261B1/en)（混淆集纠错）、
  护照 MRZ 校验位纠错、[Perfect OCR with checksums](https://www.monperrus.net/martin/perfect-ocr-digital-data)。

结论：**未见单篇覆盖"归一化数字第三匹配空间 + 校验门控 + 偏移映射回原 OCR 框遮挡 +
多空间置信级去重"全组合**。权利要求须避开 CN113128504A 的"替换生成候选 + 校验规则
匹配"表述，落点在"匹配空间构造 + 映射回遮挡 + 去重归因"。

## 机制五（四边形外扩凸包遮挡）— 评级：中低

- [midecal_tool（开源）](https://github.com/CodeChatter/midecal_tool)（另见
  [CSDN 介绍](https://blog.csdn.net/qq_45363655/article/details/160137128)）：基于
  OCR 文本行**四点框**生成跟随倾斜的遮挡区域，"不是粗暴盖矩形"。概念层已公开；
  但按单个文本行四点直接填充，未见"组内多框顶点沿远离质心方向外扩后取凸包"的
  组级构造。
- [Orekondy et al., CVPR 2018](https://arxiv.org/abs/1712.01066)：文本区域凸包 +
  DenseCRF 细化用于隐私遮挡；构造方式不同（分割掩码膨胀，非四边形顶点外扩）。
- 四边形文本检测（Quadbox 等）为公知技术；未检索到针对"外扩+凸包遮挡区域构造"
  的专利（中英文多组无命中）。

结论：概念无新意，新颖性仅剩几何构造细节，**只适合作从属权利要求，不宜单独主张**。

## 机制六（文档类型自适应级联）— 评级：中（相对最安全）

- [US9195853B2 Automated document redaction](https://patents.google.com/patent/US9195853B2/en)：
  其 data type 是内容数据类型而非文档版式类型，无类型→规则子集级联、无两级兜底。
- 商业产品已公开概念：[Klippa](https://www.klippa.com/en/blog/information/automated-document-redaction/)
  （OCR→分类发票/收据/证件→对应脱敏逻辑）、[Lawbot 脱敏猫](https://www.lawbotai.cn/docs.html)
  （自动识别文档类型选模型）。
- [CN115688151B 脱敏复敏方法](https://patents.google.com/patent/CN115688151B/zh)：
  规则场景化选择，但仅终端机**文本**数据（权利要求明确图像不支持复敏）。

结论：**未找到单篇专利覆盖"零模型轻量类型判定 → 规则子集 + 字段标签兜底 + 像素带
兜底的级联"**；概念已被产品公开，专利化程度低，发明点在实现组合。

## 机制七（可逆脱敏账本）— 评级：低-中（偏低）

- [US20240202865A1 Image obfuscation（Palantir）](https://patents.google.com/patent/US20240202865A1/en)：
  密钥可逆像素变换 + 密钥/位置存 access profile（sidecar）+ 权限校验后解密可见。
  **"密钥 + sidecar 元数据 + 授权解密的可逆图像遮挡"概念层已被披露**；但混淆像素
  保留原图内（像素变换），无独立加密账本、无 AES-GCM/独立 nonce、无贴回还原 API。
- [CN119743558A 轻量级可恢复的图像数据脱敏](https://patents.google.com/patent/CN119743558A/zh)：
  区域像素 XOR 一次一密 + LSB 把恢复参数嵌入脱敏图自身（隐写式），非独立账本。
- [CN113779630A](https://patents.google.com/patent/CN113779630A/zh)（DICOM 医疗图像
  可逆脱敏，场景特定）、CN122578214A（奇虎，文本令牌式可逆脱敏，非图像）、
  [RE-Dact](https://github.com/anshikkumartiwari/re-dact)（开源，加密+元数据+解密
  概念已公开）。

结论：具体工程实现（裁剪像素块→PNG→AES-256-GCM 独立 nonce→配对账本→还原 API）
未被单篇完整披露，但各要素均为常规手段；**预期审查中会被引用 Palantir 申请**，需按
系统权利要求 + 答辩准备。

## 总体结论

| 机制 | 最强先有技术 | 单篇全覆盖？ | 评级 |
| --- | --- | --- | --- |
| 二 混淆归一化+校验门控 | CN113128504A + Presidio | 否 | 中 |
| 五 外扩凸包遮挡 | midecal_tool + CVPR2018 | 否 | 中低 |
| 六 类型自适应级联 | Klippa/Lawbot + CN115688151B | 否 | 中 |
| 七 可逆账本 | US20240202865A1 + CN119743558A | 否 | 低-中 |

四个机制均无单篇先有技术完整覆盖（即没有发现直接摧毁新颖性的专利），但二、五、七
各有一篇"几乎同概念"的强先有技术，权利要求必须做特征级规避。策略建议：

1. **主申请**以机制一+二+三+四+五+六的完整方法为发明（独立权利要求落在多匹配空间
   + 多级兜底 + 偏移回映射的整体组合上，这是单篇先有技术都没覆盖的层面），
   五、六作从属权利要求；
2. **机制七单独一件**，按系统权利要求撰写并预做针对 Palantir 引用的答辩口径;
3. 提交前由代理机构出正式查新报告，并以同基准压测量化机制二/五/六的召回/误遮增益。
