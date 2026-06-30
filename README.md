# 毛概选择题刷题器

这是一个 Tkinter 桌面刷题程序，题库在 `questions_data.py`，主程序入口是 `maogai_quiz.py`。

## 启动方式

在 PowerShell 中进入项目目录：

```powershell
cd D:\毛概\毛概选择题题库
```

如果本机 `python` 命令可用：

```powershell
python .\maogai_quiz.py
```

如果当前环境没有配置 `python`，可以使用 Codex 自带的 Python：

```powershell
& 'C:\Users\41143\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\maogai_quiz.py
```

## 基本使用

- 左侧题号导航：点击题号可直接跳到原始题号。
- 中间答题区：题干前会标明 `【单选】` 或 `【多选】`；点击选项或按 `A/B/C/D/E` 只会选择答案，不会立即判题。
- 多选题：点击或按键会切换选中状态，再点同一选项可取消。
- 检查答案：点击“检查”或按 `Enter`。
- 下一题：判题后再次按 `Enter`，或点击“下一题”。
- 上一题/下一题：按 `←` / `→`。
- 标记错题：点击“标记错题”；再次点击可取消手动标记。

## 设置与进度

点击右上角“设置”可以打开设置面板：

- 出题模式：支持“顺序出题”和“随机出题”。
- 自动保存：默认开启。
- 保存当前进度：立即写入 `quiz_progress.json`。
- 加载之前的进度：读取 `quiz_progress.json` 并恢复答题状态。
- 重置进度：二次确认后先生成 `summary/summary-YYYYMMDD-HHMMSS.md`，再清空答题状态、错题标记和当前位置。

`quiz_progress.json` 是运行时自动生成的进度文件，不需要手动创建，也不应作为题库数据修改。
`summary/` 目录下的 Markdown 文件是重置前的错题快照，记录自动错题和手动标记题。

## 文件说明

- `maogai_quiz.py`：主程序入口，包含界面、答题流程、键盘事件和进度逻辑。
- `questions_data.py`：题库数据，只保存 `questions = [...]`。
- `quiz_progress.json`：运行时进度文件，启动或保存后自动生成。
- `summary/summary-YYYYMMDD-HHMMSS.md`：重置进度前自动生成的错题快照。
- `test_maogai_quiz.py`：核心逻辑和交互行为测试。

## 验证

运行测试：

```powershell
& 'C:\Users\41143\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest test_maogai_quiz.py
```

运行语法检查：

```powershell
& 'C:\Users\41143\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile maogai_quiz.py questions_data.py test_maogai_quiz.py
```

## 常见问题

- 启动时报找不到 `python`：使用上面的 Codex 自带 Python 命令，或安装 Python 3 并加入 PATH。
- 进度异常：程序会提示并从头开始；也可以在设置面板中点击“重置进度”。
- 不要编辑题库文本：题库内容集中在 `questions_data.py`，本项目不手工纠错题目、选项、答案或解析。
