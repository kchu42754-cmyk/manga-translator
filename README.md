# 本地漫画汉化助手

这套工具默认复用你已经部署在 WSL 里的 `Qwen-VL + vLLM`。现在它已经分成两层：

- 命令行批量翻译
- 本地网页汉化台

目标不是一次性做成全自动抹字排字，而是先让你能够很顺手地：

- 直接贴截图
- 直接拖整话文件夹
- 保存固定区域后重复翻译同一块位置
- 拿到适合校对和后续嵌字的中文稿

## 目录说明

- `manga_translate.py`
  - 核心脚本，支持单张图片或整文件夹批量翻译。
- `translate_manga.ps1`
  - Windows 启动器，会先检查本地接口；如果没在线，就调用你现有的 `~/workspace/start_vllm.sh` 拉起模型。
- `manga_hub.py`
  - 本地网页后端，支持上传、粘贴、后台任务和结果下载。
- `launch_manga_hub.ps1`
  - 网页启动器，会在后台拉起本地网页，并自动打开浏览器。
- `start_manga_hub.cmd`
  - 适合双击启动的入口。
- `requirements.txt`
  - 这套工具依赖的 Python 包。

## 网页版启动

如果你换了 Python 环境，可以先装依赖：

```powershell
python -m pip install -r .\requirements.txt
```

最省事的方式是直接双击：

```text
start_manga_hub.cmd
```

或者在 PowerShell 里运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\launch_manga_hub.ps1
```

默认行为：

- 打开本地网页 `http://127.0.0.1:7861`
- 如果网页服务还没启动，就先启动网页服务
- 如果 Qwen 没在线，网页会自动尝试拉起默认的 `7B`

网页里目前支持：

- 拖拽图片
- 选择整文件夹
- Ctrl+V 粘贴截图
- 在预览图上框选固定区域
- 把固定区域保存到浏览器，下次继续用
- 下载整包 ZIP / Markdown / CSV / JSON

固定区域的用法更适合这些场景：

- 你经常截同一个阅读器窗口
- 对白总在相近位置
- 你只想翻页中某一块，不想让模型看整张图

## 命令行快速开始

1. 把一话漫画放进同一个文件夹，比如 `D:\漫画\第01话`
2. 在当前目录打开 PowerShell，运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\translate_manga.ps1 -InputPath "D:\漫画\第01话"
```

3. 结果会默认输出到旁边的新文件夹，例如：

```text
D:\漫画\第01话_translation
```

里面会有这些文件：

- `chapter_translation.md`
  - 适合直接阅读和整理的整话翻译稿。
- `chapter_translation.csv`
  - 适合用 Excel 打开后继续修稿。
- `chapter_translation.json`
  - 结构化汇总结果。
- `每页文件名.json / .md / .raw.txt`
  - 单页结果和原始模型回复。

翻译结果目前是“单独输出”的：

- 不会直接把中文贴回漫画原图
- 更适合你先校对、润色，再去修图软件里嵌字

## 常用命令

只跑前 3 页试试看：

```powershell
powershell -ExecutionPolicy Bypass -File .\translate_manga.ps1 -InputPath "D:\漫画\第01话" -Limit 3
```

指定输出目录：

```powershell
powershell -ExecutionPolicy Bypass -File .\translate_manga.ps1 -InputPath "D:\漫画\第01话" -OutputDir "D:\漫画\第01话\汉化稿"
```

如果你已经自己启动了模型接口，也可以直接调用 Python：

```powershell
python .\manga_translate.py "D:\漫画\第01话" --endpoint http://127.0.0.1:8001/v1
```

## 你当前这套 Qwen 部署

我检查到你在 WSL 里已经有现成启动脚本：

- `~/workspace/start_vllm.sh 7b`
  - 启动 `qwen2-vl-7b-local`，端口 `8001`
- `~/workspace/start_vllm.sh 30b`
  - 启动 `qwen3-vl-30b-local`，端口 `8000`

`translate_manga.ps1` 会优先尝试连接已在线接口；如果都没在线，就默认启动 `7b`。

## 适合这个工具的用法

- 用它先做“看图识字 + 初版汉化”
- 再从 `chapter_translation.md` 或 `chapter_translation.csv` 里手动润色
- 最后在你熟悉的修图软件里抹字、嵌字

## 目前的边界

- 它现在专注”辅助汉化”，还不包含自动擦字、修复背景、自动排版
- 网页版已经支持”固定区域”，但还没有做成全局热键呼出或系统级框选翻译
- 花体字、极小字、扭曲拟声词可能需要你手动校正
- 如果 Qwen-VL 对整张图片拒答，建议改成”先 OCR 提取日文，再让 Qwen 只翻译文本”的两段式流程
- 如果你后面想继续做成”自动抹字 + 回填中文”的半自动流程，我们可以在这套基础上继续加

## 最近更新 (2025-03)

- **英文 Prompt**：默认使用英文 prompt 以解决 Qwen-VL 7B 的中文编码问题
- **max_tokens 4000**：增加默认 token 数量以支持更完整的 JSON 输出
- **改进错误提示**：模型服务离线时提供更友好的中文排查指引
