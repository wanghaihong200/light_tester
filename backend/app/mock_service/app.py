"""Mock 子进程服务:一实例一进程,监听实例端口,每请求实时读库匹配。"""
import argparse
import asyncio
import json
import os
import sys
import threading
import time
from urllib.parse import parse_qs

import uvicorn
from fastapi import FastAPI, Request, Response

from app.database import SessionLocal
from app.mock_service.matching import pick_rule
from app.mock_service.templating import render_template
from app.models import MockHit, MockInstance, MockRule

HIT_KEEP_PER_INSTANCE = 1000
HIT_BODY_MAX = 64 * 1024
DEFAULT_MISS_BODY = '{"error":"no mock rule matched"}'
ALL_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]
_PARENT_WATCH_SECONDS = 5.0


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "*",
        "Access-Control-Allow-Headers": "*",
    }


def _trim_hits(db, instance_id: int) -> None:
    db.flush()  # autoflush=False:先把本请求待插的 hit 落库,滚动淘汰才能将其计入(否则保留数会超 1000)
    boundary = (db.query(MockHit.id)
                .filter(MockHit.instance_id == instance_id)
                .order_by(MockHit.id.desc())
                .offset(HIT_KEEP_PER_INSTANCE).limit(1).scalar())
    if boundary is not None:
        (db.query(MockHit)
         .filter(MockHit.instance_id == instance_id, MockHit.id <= boundary)
         .delete(synchronize_session=False))


def create_mock_app(instance_id: int) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    def _check_token(instance: MockInstance | None, token: str) -> bool:
        return instance is not None and bool(token) and token == instance.token

    @app.get("/__mock_health__")
    def health(token: str = ""):
        with SessionLocal() as db:
            if _check_token(db.get(MockInstance, instance_id), token):
                return {"ok": True, "instance_id": instance_id}
        return Response(status_code=403)

    @app.post("/__mock_shutdown__")
    def shutdown(token: str = ""):
        with SessionLocal() as db:
            if _check_token(db.get(MockInstance, instance_id), token):
                server = getattr(app.state, "server", None)
                if server is not None:
                    server.should_exit = True
                return {"ok": True}
        return Response(status_code=403)

    @app.api_route("/{full_path:path}", methods=ALL_METHODS)
    async def serve(request: Request, full_path: str):
        t0 = time.monotonic()
        method, path = request.method, "/" + full_path
        query = parse_qs(request.url.query, keep_blank_values=True)
        headers: dict[str, list[str]] = {}
        for k, v in request.headers.items():
            headers.setdefault(k.lower(), []).append(v)
        body = await request.body()
        with SessionLocal() as db:
            instance = db.get(MockInstance, instance_id)
            if instance is None or instance.is_deleted:
                return Response(content="mock instance removed", status_code=404)
            rules = (db.query(MockRule)
                     .filter(MockRule.instance_id == instance_id,
                             MockRule.is_deleted.is_(False), MockRule.enabled.is_(True))
                     .order_by(MockRule.sort_order.asc(), MockRule.id.asc()).all())
            rule, path_vars = pick_rule(rules, method, path, query, headers, body)
            if method == "OPTIONS" and instance.cors_enabled:
                return Response(status_code=204, headers=_cors_headers())  # 预检不耗规则不记日志
            hold_error = None
            delay_ms = rule.delay_ms if rule else 0
            if rule is not None and rule.timeout_enabled:
                await asyncio.sleep(rule.timeout_seconds)  # 挂住不回;客户端超时自断
                hold_error = "timeout-simulated"
            elif delay_ms:
                await asyncio.sleep(delay_ms / 1000)
            if rule is None:
                status_code = instance.default_status or 404
                payload = instance.default_body or DEFAULT_MISS_BODY
                headers_out: dict[str, str] = {}
                content_type = "application/json"
            else:
                status_code = rule.response_status
                headers_out = {str(k): str(v) for k, v in (rule.response_headers or {}).items()}
                content_type = headers_out.pop("content-type", None)
                payload = rule.response_body or ""
                if rule.enable_template:
                    try:
                        body_json = json.loads(body.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                        body_json = None
                    payload = render_template(payload, path_vars=path_vars, query=query,
                                              headers=headers, body_json=body_json)
            resp = Response(content=payload, status_code=status_code,
                            media_type=content_type, headers=headers_out)
            if instance.cors_enabled:
                for k, v in _cors_headers().items():
                    resp.headers[k] = v
            elapsed = int((time.monotonic() - t0) * 1000)
            db.add(MockHit(instance_id=instance_id,
                           rule_id=rule.id if rule else None,
                           method=method, path=path[:500],
                           query=request.url.query[:1000] if request.url.query else None,
                           request_headers=dict(request.headers) or None,
                           request_body=body[:HIT_BODY_MAX].decode("utf-8", "replace") if body else None,
                           matched=rule is not None, response_status=status_code,
                           delay_ms=delay_ms, elapsed_ms=elapsed, error=hold_error))
            _trim_hits(db, instance_id)
            db.commit()
            return resp

    return app


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        SYNCHRONIZE = 0x00100000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-id", type=int, required=True)
    parser.add_argument("--parent-pid", type=int, default=os.getpid())
    args = parser.parse_args()

    from app.config import settings

    with SessionLocal() as db:
        instance = db.get(MockInstance, args.instance_id)
        if instance is None or instance.is_deleted:
            print(f"instance {args.instance_id} not found", file=sys.stderr)
            sys.exit(2)
        port = instance.port

    app = create_mock_app(args.instance_id)
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning"))
    app.state.server = server

    def watch_parent() -> None:
        # 父进程(平台后端)死亡 → 自退,防孤儿占口;PID 复用漏检由平台启动对账的
        # __mock_shutdown__ 令牌关停兜底(两层防孤儿,ADR-0009)
        while _pid_alive(args.parent_pid):
            time.sleep(_PARENT_WATCH_SECONDS)
        server.should_exit = True

    threading.Thread(target=watch_parent, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
