import json, time
from groq import Groq
from .config import settings
from .tools import TOOLS, run_python
from .prompts import build_system_prompt
from .observability import get_logger

log = get_logger()
client = Groq(api_key=settings.groq_api_key)

def ask(question, df, messages=None):
    messages = messages or [{"role": "system", "content": build_system_prompt(df)}]
    messages.append({"role": "user", "content": question})
    trace = {"question": question, "steps": []}

    for step in range(settings.max_steps):
        t0 = time.time()
        resp = client.chat.completions.create(
            model=settings.model, messages=messages, tools=TOOLS, tool_choice="auto"
        )
        msg = resp.choices[0].message
        latency = round(time.time() - t0, 2)

        if not msg.tool_calls:
            trace.update(answer=msg.content, tokens=resp.usage.total_tokens)
            log.info(json.dumps(trace))
            return msg.content, messages

        messages.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [{"id": tc.id, "type": "function",
                            "function": {"name": tc.function.name,
                                         "arguments": tc.function.arguments}}
                           for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            code = json.loads(tc.function.arguments)["code"]
            result = run_python(code, df)
            trace["steps"].append({"code": code, "result": result[:500],
                                   "latency_s": latency, "error": "ERROR" in result})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result[:4000]})

    trace["answer"] = None
    log.warning(json.dumps(trace))
    return "Stopped: hit step limit.", messages
