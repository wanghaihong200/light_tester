"""Mock 响应体 Jinja2 模板渲染(纯函数)。"""
import json
import random
import time
import uuid

from jinja2 import Environment, ChainableUndefined

from jsonpath_ng.ext import parse as _jsonpath_parse

_env = Environment(undefined=ChainableUndefined)  # 平台自用工具,非对外沙箱;Undefined(含链式取值)渲染空串


def render_template(template: str, *, path_vars: dict[str, str],
                    query: dict[str, list[str]], headers: dict[str, list[str]],
                    body_json) -> str:
    def jpath(expr: str) -> str:
        try:
            found = _jsonpath_parse(expr).find(body_json)
        except Exception:
            return ""
        return _first_str(found)

    def _first_str(found) -> str:
        if not found:
            return ""
        v = found[0].value
        if isinstance(v, str):
            return v
        return json.dumps(v, ensure_ascii=False)

    ctx = {
        "path": dict(path_vars),
        "query": {k: v[0] for k, v in query.items() if v},
        "header": {k: v[0] for k, v in headers.items() if v},
        "body": body_json,
        "uuid4": lambda: str(uuid.uuid4()),
        "now_ts": lambda: int(time.time()),
        "rand_int": lambda a, b: random.randint(a, b),
        "jpath": jpath,
    }
    return _env.from_string(template).render(**ctx)
