"""tools.py —— 工具箱:模型能干的所有实际操作都在这。

模型只会"说":"我要读 sample.txt"。
真正打开文件的,是这个文件里的函数。

以后要加新工具,一共三步:
    1. 写一个函数(干活的)
    2. 在 TOOLS 清单里加一条说明(让模型知道有这个工具)
    3. 在 HANDLERS 表里加一行(把工具名连到函数)
"""
import difflib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


# ==========================================================
#  工具清单 —— 发请求时会一起发给 DeepSeek
#  模型看了这份清单,才知道自己能调什么工具、每个工具要填什么参数。
#  这份内容是写给模型看的,不是给你看的。
# ==========================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取工作目录下的一个文本文件。改文件之前一定要先读。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的相对路径,例如 sample.txt",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "修改一个已存在的文件:把 old_string 换成 new_string。"
                "只改一处,而且 old_string 必须在文件里只出现一次 —— "
                "所以要带上足够的上下文(比如整行代码连缩进),让它独一无二。"
                "如果失败,会告诉你原因,请先 read_file 看清楚原文再重试。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的相对路径",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要被替换掉的原文,必须和文件里的内容完全一致",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换成的新内容",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出一个文件夹里有哪些文件和子文件夹。想知道有什么文件时,先用这个。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件夹路径,填 . 表示当前文件夹",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_size",
            "description": "查看一个文件的大小,返回多少字节。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件的相对路径,例如 key.txt",
                    },
                },
                "required": ["path"],  # ← 必须给
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "运行工作目录下的一个 Python 文件,返回它的全部输出和报错。"
                "改完代码之后,运行它来验证改动是否正确。最多运行 15 秒。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要运行的 .py 文件,例如 buggy.py",
                    },
                },
                "required": ["path"],
            },
        },
    },

]


# ==========================================================
#  工具函数 —— 真正干活的
# ==========================================================
def _safe_path(path):
    """检查路径有没有跑出 minicoder 文件夹。

    跑出去了就报错。这样模型不管怎么折腾,都只能动这个文件夹里的东西,
    碰不到你电脑上别的地方。
    """
    full = os.path.abspath(os.path.join(HERE, path))
    if full != HERE and not full.startswith(HERE + os.sep):
        raise ValueError("路径越界:只允许操作 " + HERE + " 里面的文件")
    return full


def read_file(path):
    with open(_safe_path(path), encoding="utf-8") as f:
        return f.read()


def edit_file(path, old_string, new_string):
    """把文件里的一段文字换成另一段。

    改之前先检查两件事,任何一件不过就拒绝改,直接返回错误说明。
    """
    full = _safe_path(path)

    with open(full, encoding="utf-8") as f:
        original = f.read()

    # 检查 1:文件里根本找不到这段文字
    # -> 说明模型记错了原文,不让它凭感觉瞎改
    hits = original.count(old_string)
    if hits == 0:
        return "错误:文件里找不到这段内容。请先用 read_file 看清原文,再动手改。"

    # 检查 2:这段文字出现了好几次
    # -> 不知道它想改哪一处,让它多带几行上下文重新说清楚
    if hits > 1:
        return (
            "错误:这段内容在文件里出现了 "
            + str(hits)
            + " 次,无法确定你要改哪一处。请多带上几行上下文,让它变成唯一的。"
        )

    # 两个检查都过了:先在内存里改好,先不写进文件
    updated = original.replace(old_string, new_string, 1)
    diff = make_diff(path, original, updated)

    # 写进去之前,先问人。人不同意就不改
    if not ask_permission(path, diff):
        return "用户拒绝了这次修改,文件没有被改动。"

    with open(full, "w", encoding="utf-8") as f:
        f.write(updated)

    return "已修改 " + path + "\n" + diff


def make_diff(path, old_text, new_text):
    """算出改动前后的对比。

    每行开头是 - 表示删掉的,+ 表示新加的。
    """
    lines = difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        fromfile=path + " (改前)",
        tofile=path + " (改后)",
        lineterm="",
        n=2,                      # 改动位置的上下各显示 2 行,方便看出改的是哪儿
    )
    return "\n".join(lines)


def list_dir(path="."):
    """列出文件夹里有哪些文件和子文件夹。"""
    full = _safe_path(path)
    names = os.listdir(full)
    if not names:
        return "(空的,里面什么都没有)"
    return "\n".join(sorted(names))

def file_size(path):
    """报告一个文件有多少字节。"""
    full = _safe_path(path)
    size = os.path.getsize(full)
    return "文件大小:" + str(size) + " 字节"


def run_python(path):
    """运行工作目录下的一个 Python 文件,把屏幕输出原样带回来。

    这是四个工具里最危险的一个:它是真的在执行代码。
    所以有两道防护:
        1. 只允许运行 minicoder 文件夹里的文件(_safe_path 管)
        2. 最多跑 15 秒,防止死循环把电脑卡死
    """
    full = _safe_path(path)

    # PYTHONIOENCODING=utf-8:强制子程序用 UTF-8 输出中文。
    # 不加的话 Windows 下子程序默认用 GBK,中文会变成乱码。
    env = dict(os.environ, PYTHONIOENCODING="utf-8")

    try:
        result = subprocess.run(
            [sys.executable, full],
            capture_output=True,          # 把子程序打印的所有内容接住
            text=True,
            encoding="utf-8",
            errors="replace",             # 遇到解不开的字节就换成 ?,不让程序崩
            timeout=15,                   # 15 秒还跑不完就杀掉
            cwd=HERE,                     # 让它在自己家里跑,别乱跑相对路径
            env=env,
        )
    except subprocess.TimeoutExpired:
        return "错误:程序运行超过 15 秒被强制停止(多半是死循环)。"

    # stdout 是正常打印,stderr 是报错信息,拼在一起给模型看
    output = (result.stdout or "") + (result.stderr or "")

    # 输出太长就截断,防止一次塞爆模型的上下文
    if len(output) > 2000:
        output = output[:2000] + "\n...(输出太长,已截断)"

    if result.returncode == 0:
        return "程序运行成功,输出:\n" + output
    return "程序出错了(退出码 " + str(result.returncode) + "):\n" + output


# ==========================================================
#  工具登记表 —— 工具名 -> 函数
#  模型报一个名字,就从这张表里找对应的函数来执行。
# ==========================================================
HANDLERS = {
    "read_file": read_file,
    "edit_file": edit_file,
    "list_dir": list_dir,
    "file_size": file_size,
    "run_python": run_python,
}


def ask_permission(path, diff):
    """把改动摆出来,问过人才写。"""
    print()
    print("========== 它想修改 " + path + " ==========")
    for line in diff.splitlines():
        print("  " + line)
    print("======================================")

    answer = input("  同意这次修改吗?(y = 同意 / n = 拒绝): ").strip().lower()
    return answer == "y"


def run_tool(name, arguments):
    """按名字找到函数,执行,返回结果。

    注意:工具出错了不抛异常,而是把错误原因变成一句话返回。
    因为模型看到"文件不存在"这种原因,会自己换个办法再试;
    要是程序直接崩了,它连试的机会都没有。
    """
    handler = HANDLERS.get(name)
    if handler is None:
        return "错误:没有叫 " + name + " 的工具。"

    try:
        return handler(**arguments)
    except Exception as exc:
        return "工具执行失败:" + type(exc).__name__ + ":" + str(exc)
