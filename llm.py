"""llm.py —— 所有跟 DeepSeek 服务器打交道的代码。

调用大模型,说白了就是:发一个网络请求,收一个回答,没了。

这个文件干三件事:
    1. 把对话整理成 DeepSeek 要求的格式,发出去
    2. 接收回答
    3. 把回答拆成我们好用的样子

以后想换别的模型(通义、Kimi),只改这个文件,别的文件不用动。
"""
import json
import os
import urllib.error
import urllib.request

import tools                       # 发请求时要带上工具清单,清单在 tools.py 里

HERE = os.path.dirname(os.path.abspath(__file__))

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"


def load_api_key():
    """找 API key:先看环境变量,没有就看同目录的 key.txt 文件。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key

    path = os.path.join(HERE, "key.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            key = f.read().strip()
        if key:
            return key

    raise SystemExit(
        "没找到 API key,两种办法任选:\n"
        "  1. 在同目录建一个 key.txt,里面只写一行 sk-...\n"
        "  2. 设置环境变量 DEEPSEEK_API_KEY"
    )


def ask_model(messages):
    """把整段对话发给 DeepSeek,拿回它的回答。"""
    # 请求的内容。messages 是全部对话历史,tools 是工具清单
    body = {
        "model": MODEL,
        "messages": [_to_api(m) for m in messages],
        "tools": tools.TOOLS,
    }

    # 就是发一个普通的网络请求,跟打开网页一个道理,只是内容是 JSON
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            # 密钥放在请求头里,服务器靠它知道你是谁、扣谁的钱
            "Authorization": "Bearer " + load_api_key(),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 服务器拒绝了(比如 key 不对、格式不对),把它的原话打出来
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit("请求被拒绝(HTTP " + str(exc.code) + "):\n" + detail)

    # DeepSeek 的回答在 choices[0].message 里,拆成我们好用的格式
    return _from_api(payload["choices"][0]["message"])


def _to_api(message):
    """发出去之前,把我们的格式转成 DeepSeek 要求的格式。

    两边几乎一样,就一个区别:工具参数必须是一段文字(字符串),
    不能是 Python 字典。
    """
    if message["role"] == "assistant" and message.get("tool_calls"):
        return {
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        # DeepSeek 要求 arguments 是一段文字,
                        # 所以用 json.dumps 把字典变成文字
                        "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                    },
                }
                for call in message["tool_calls"]
            ],
        }
    return message


def _from_api(message):
    """收回来时反着转:DeepSeek 给它的格式,我们拆成好用的。

    主要工作是把工具参数从一段文字转回字典,这样后面调函数才方便。
    """
    reply = {"role": "assistant", "content": message.get("content") or ""}

    calls = message.get("tool_calls") or []
    if calls:
        reply["tool_calls"] = [
            {
                "id": call["id"],
                "name": call["function"]["name"],
                # json.loads 干的事:把 '{"path": "sample.txt"}'
                # 这段文字变回 {'path': 'sample.txt'} 这个字典
                "arguments": json.loads(call["function"]["arguments"] or "{}"),
            }
            for call in calls
        ]
    return reply
