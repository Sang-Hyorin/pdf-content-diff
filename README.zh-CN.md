# PDF Content Diff

**把实际文字修改整理成清晰的左右对比 PDF。**

![虚构示例](docs/preview.png)

红色表示删除或被替换的文字，黄色表示新增或替换后的文字。
工具先对整份文档进行文字匹配，再展示有改动的区域和必要上下文。
页边行号、页码和换行造成的位移会尽量过滤。

## 命令行使用

需要 Python 3.9 或更新版本：

```sh
python -m pip install -r requirements.txt
python build_comparison.py older.pdf newer.pdf comparison.pdf
```

生成的文件保留矢量文字，可以选中、复制并放大查看。
两份输入 PDF 不会被保存或覆盖。相同输入会复用缓存。

## VS Code 使用

1. 从 [Releases](https://github.com/Sang-Hyorin/pdf-content-diff/releases) 下载 VSIX，
   运行 **Extensions: Install from VSIX** 安装。
2. 在 Python 环境中安装 `requirements.txt`，设置 `pdfContentDiff.pythonPath`。
3. 安装 PDF 阅读器扩展，例如 `mathematic.vscode-pdf`。
4. 运行 **PDF Content Diff: Compare Two PDFs**，依次选择旧稿与新稿。
5. 后续可运行 **PDF Content Diff: Compare Last Pair** 重新比较。

结果保存在新稿旁边，名称为 `<name>_content_comparison.pdf`。
只有本工具生成的结果文件可以被更新，不会覆盖同名的无关文件。

使用 Remote SSH 时，将扩展安装在远端，并指定远端 Python。
比较在服务器上完成，客户端只打开轻量的结果 PDF。
项目目前没有发布到 VS Code Marketplace。

## 能力边界

本工具比较文字，不检测纯图片、矢量图形、字体或版式的变化，也不做 OCR。
多栏阅读顺序、旋转页面和部分数学符号可能影响匹配。
行号识别采用位置启发式；字母之间的连字符会归一化，仅连字符变化可能被忽略。
达到长度阈值的完全相同文本移动会被过滤。重要公式仍需人工核对原稿。

示例全部为虚构内容。源代码不含服务器路径、私有稿件、密钥或 API 调用。
项目采用 **AGPL-3.0-only**，使用 PyMuPDF。完整说明见 [英文 README](README.md)。

## 自动刷新

首次比较后会监听两份输入 PDF，文件停止变化后等待约 1.5 秒重新生成对比。使用推荐的 PDF 阅读扩展打开对比文件即可自动重载，后台刷新不会抢焦点。同一工作区重启后恢复监听。设置 `pdfContentDiff.autoRefresh` 可关闭，`pdfContentDiff.refreshDelay` 可调整等待时间。修改 LaTeX 后仍需先编译生成新稿 PDF；工具不修改源 PDF。
