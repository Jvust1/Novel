# 参考文本完整读取

旧 TXT/MD 读取器固定用 UTF-8 并忽略无法解码的字节。实际复现中，同一原创句子保存为 GB18030 或 UTF-16 后会变成丢字和乱码，却仍标成 `utf8`，随后进入风格统计、Reference Pack 或原创性对比。这次在这些真实入口前共同拦住这种情况。

## 在 GPT 里的使用方法

拿到参考文件时先核对格式和原件是否可读。若已经有明确编码，使用它；若带标准 UTF-8/16/32 BOM，按明确字节顺序读取；没有 BOM 时默认严格尝试 UTF-8。失败就保留原件，列出本地统计候选，并让作者核对或明确选择，不能丢掉坏字节继续分析。

GitHub 插件读取规则不等于执行了解码器。只有取得原文件字节且有真实执行器时才报告完整字节校验；如果工具只提供已经抽取的文本，就注明原始编码未验证，不伪造哈希，不要求作者安装本地界面。真实作品、参考原件和派生结果继续按授权存到私有位置。

默认 UTF-8 是一项明确约定，不证明文件原本一定使用 UTF-8。不同编码可能都能完整解码相同字节而得到不同文本；统计分数和可逆性都不能代替核对原件。已经成为合法 Unicode 的乱码，也不能由本检查自动恢复。

## 读取时会检查什么

- UTF-32 BOM 先于 UTF-16 检查，避免共享前缀误判；明确选择与 BOM 冲突时停止
- 所有字节都必须严格解码，重新按相同编码和原 BOM 编码后必须逐字节相同；不使用 ignore 或 replace
- 无 BOM 的 UTF-16/32 需要明确字节顺序；NUL/异常控制字符或损坏的末尾不能进入分析
- 保留原正文换行、空白及正文内部 BOM 字符，只把开头编码 BOM 作为编码元数据处理
- 返回原文件完整 SHA-256、解码后 UTF-8 SHA-256、编码、BOM、决定方式及可逆验证结果；这些报告不含参考正文

chardet 7.6.0 实际参与本地候选排序。统计最多检查 200,000 字节，但每个候选还必须对完整文件严格解码并回编码；尾部坏字节不能躲在统计窗口之外。即使只剩一个候选或置信度很高，也不会自动选它。当前支持常用 Unicode、GB18030/GBK/GB2312、Big5 和 Windows-1252 等明确选项。

## 已连接的三个入口

1. **Style Lab**：可明确选择 TXT/MD 原文件编码。读取失败会在模型调用、风格入库和保存前停止；旧风格资料保留。项目、文件名或实际字节改变时，旧编码选择重置为默认，需要针对新原件核对。粘贴的 Unicode 文本不经过字节猜测
2. **Reference Pack**：`build_reference_source(..., encoding="gb18030")` 接收明确选择。旧三元组输入保持兼容；混合编码可给四元组 `(filename, data, weight, encoding)`。保存的派生 profile 增加解码证据，不保存参考正文
3. **原创性 CLI**：目标和参考可分别指定编码。相同正文分别存为 UTF-8 和 GB18030，明确读取后得到相同文本/签名，不再把乱码拿来比较

既有 DOCX/PDF/HTML 等复杂格式提取器仍按原流程工作；本次不声称解决 OCR、表格遗漏或所有高级读取器的内容完整性。显式纯文本编码不能偷偷作用于这些格式。

## 有执行器时的例子

```python
from novel_ai.reading import extract_reference
result = extract_reference("reference.txt", actual_original_bytes, encoding="gb18030")
text = result.text
evidence = result.decoding
```

输入必须是实际取得的原字节。首次默认读取失败会抛出 `EncodingSelectionRequired`，其候选只是选择建议；错误不会返回部分正文。

```bash
python scripts/build_reference_pack.py first.txt second.txt --out private-pack.json \
  --encoding first.txt gb18030
python scripts/check_originality.py --target draft.txt --reference notes.pdf --reference reference.txt \
  --reference-encoding auto --reference-encoding gb18030 --output private-review.json
```

Reference Pack 的编码选择绑定具体输入路径，可重复提供；未知路径或重复选择会失败。原创性检查的参考编码按 `--reference` 顺序一一对应，`auto` 保留 UTF-8/BOM 或复杂格式原读取方式；目标单独用 `--target-encoding`。全部输入读取成功前不会覆盖已有输出；不要将这条保证扩大到后续任意磁盘错误或所有保存事务。

## 证据和限制

测试只用原创合成文本，覆盖 UTF BOM/端序冲突、GB18030、Big5 的非可逆映射、窗口后损坏、错误候选、同名文件换版本、混合格式 CLI 和真实 AppTest 按钮。失败时旧资料不变，且不会发起模型请求；正确选择后沿原分析链继续。

完整结果见 [候选记录](../governance/reference_decoding_candidate.json)。实际千星来源、精确版本与完整许可证见 [NOTICE](../third_party/chardet-reference-decoding/NOTICE.md)。这只是输入完整性，不证明风格学习、相似度阈值、原创性结论或文学质量本身正确。
