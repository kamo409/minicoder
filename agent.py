"""agent.py —— 主循环,agent 从这里启动。

这个文件只干一件事:反复地"问模型 -> 执行 -> 再问模型"。

模型怎么联系,在 llm.py 里;文件怎么读写,在 tools.py 里。
这里都不管,只管按顺序走流程:

    1. 把目前的对话发给模型,问它下一步想干嘛
    2. 它说"我要读文件" -> 我们真去读,把内容告诉它,回到第 1 步
    3. 它直接回答了问题(没要求调工具) -> 结束

跑法:
    python agent.py                      # 对话模式:打开就聊,关掉自动存盘
    python agent.py "你的任务"            # 单次任务:干完这一件就退出
    python agent.py --fix                # 老演示:造个坏文件让 agent 修
"""
import json
import os
import sys

import llm
import tools

# 对话记录存到这个文件里。程序关了它还在,下次 --continue 就能接上
SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session.json")

DEFAULT_TASK = (
    "buggy.py 里的 find_max 函数有 bug:当列表里全是负数时,它返回的结果不对。"
    "先读这个文件,找到问题,然后修好它。"
)


# ==========================================================
#  主循环 —— 整个 agent 就是下面这个 for
# ==========================================================
def run(task, max_steps=6, history=None):
    # 对话记录。模型没有记忆,每一轮都要把全部历史重新发一遍,
    # 所以它"记得"之前发生了什么,全靠这个列表越攒越长。
    # history 是上次存盘的对话:有就接着用,没有就从新任务开始
    if history:
        messages = list(history)
        messages.append({"role": "user", "content": task})
    else:
        messages = [{"role": "user", "content": task}]

    # 最多转 max_steps 圈。设上限是为了防它没完没了地调工具,一直花钱。
    for step in range(1, max_steps + 1):
        print(f"--- 第 {step} 轮:把整段对话发给模型 ---")

        reply = llm.ask_model(messages)      # 问模型:下一步干嘛
        messages.append(reply)               # 把它的回答记进对话记录

        # 回答里没有"我要调工具" -> 说明它直接把答案说出来了,收工
        if not reply.get("tool_calls"):
            print(f"[模型] {reply['content']}")
            return messages

        # 它说要调工具 -> 真去调,把结果也记进对话记录,然后转下一圈
        for call in reply["tool_calls"]:
            print(f"[调工具] {call['name']}({call['arguments']})")

            result = tools.run_tool(call["name"], call["arguments"])

            # 一行一行打印。edit_file 返回的是改动对比,挤成一行就没法看了
            text = str(result)
            for line in text.splitlines()[:12]:
                print("        " + line)
            if len(text.splitlines()) > 12:
                print("        ... (更长的输出已省略)")

            messages.append({
                "role": "tool",
                # 这行不能少,少了 DeepSeek 直接报错。它是个编号,
                # 告诉服务器"这份结果对应的是哪一次工具调用"
                "tool_call_id": call["id"],
                "content": text,
            })

    print(f"[停止] 转了 {max_steps} 圈还没干完,强制结束(防止它一直烧钱)")
    return messages


# ==========================================================
#  会话存盘 —— agent 的"记忆"就是一个 json 文件
# ==========================================================
def save_session(messages):
    """把整段对话写进 session.json。程序关了它也还在。"""
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)
    # ensure_ascii=False:让中文按原样存,不存成 \\uXXXX 的编码样子
    # indent=2:存出来的文件带缩进,人也能看懂


def load_session():
    """把上次存的对话读回来。没有存档就返回 None,当新对话开始。"""
    if not os.path.exists(SESSION_FILE):
        return None
    with open(SESSION_FILE, encoding="utf-8") as f:
        return json.load(f)


# ==========================================================
#  启动部分 —— 跟 agent 的原理没关系,只是让它能跑起来
# ==========================================================
def make_buggy_file():
    """每次运行前,造一个带 bug 的小文件,给 agent 练手用。"""
    source = '''"""一个小小的示例文件,里面藏了一个真 bug。"""


def average(numbers):
    return sum(numbers) / len(numbers)


def find_max(items):
    biggest = 0
    for x in items:
        if x > biggest:
            biggest = x
    return biggest


if __name__ == "__main__":
    print("average([1, 2, 3]) =", average([1, 2, 3]))
    print("find_max([-5, -2, -9]) =", find_max([-5, -2, -9]))
'''
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "buggy.py"),
              "w", encoding="utf-8") as f:
        f.write(source)


# ==========================================================
#  对话模式 —— 日常用法。打开就聊,关掉自动记住
# ==========================================================
def chat():
    """像聊天软件一样:一句一句对,退出时把对话存进 session.json。"""
    history = load_session()
    if history:
        print(f"[接上] 读回了上次存下的 {len(history)} 条记录,接着聊。")
    else:
        print("[新对话] 没找到存档,从头开始。")

    print("输入 exit(或按 Ctrl+C)退出,对话会自动存盘。")
    print("模式:真模型(" + llm.MODEL + ")\n")

    try:
        while True:
            try:
                user_input = input("你> ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q", "退出"):
                break

            # 把这句交给主循环跑。跑完拿回完整对话,存一次盘。
            # 每句存一次,就算程序中途崩了,之前的也都在。
            history = run(user_input, history=history)
            save_session(history)
            print()

    except KeyboardInterrupt:
        print()

    # 就算一句话都没说,也存个空档,下次打开就是干净的新对话
    save_session(history or [])
    print("[已存盘] 下次打开自动接上。再见!")


def main():
    args = sys.argv[1:]

    # 什么都不带 -> 对话模式,这是日常用法
    if not args:
        chat()
        return

    # --fix -> 老演示:造个坏文件让 agent 修,验证它还正常
    if args == ["--fix"]:
        make_buggy_file()
        print("模式:真模型(" + llm.MODEL + ")")
        print("任务:" + DEFAULT_TASK)
        print()
        messages = run(DEFAULT_TASK)
        save_session(messages)
        print()
        print("[已存盘] 下次打开对话模式,它还记得这次修了什么")
        return

    # 其余情况:命令行后面的字当一次性任务
    history = None
    if "--continue" in args:
        args.remove("--continue")
        history = load_session()
        if history:
            print(f"[接上] 读回了上次存下的 {len(history)} 条对话记录")
        else:
            print("[提示] 没找到存档,当新对话开始")

    task = " ".join(args)
    print("模式:真模型(" + llm.MODEL + ")")
    print("任务:" + task)
    print()
    messages = run(task, history=history)

    save_session(messages)
    print()
    print("[已存盘] 对话记录保存在 session.json,下次打开对话模式自动接上")


if __name__ == "__main__":
    main()
