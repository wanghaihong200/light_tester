# app/jobs/api_gen.py
"""接口生成 handler:读文档→AI 流式→写盘→mvn 自检→修复轮→artifacts 落库→SSE 阶段事件。

mvn 自检:失败喂编译错误回 AI 修复,≤2 轮仍败→job failed(已写文件保留)。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.client import estimate_cost, stream_api_generation
from app.config import settings
from app.database import SessionLocal
from app.jobs.bus import bus
from datetime import datetime

from app.jobs.pipeline import _strip_code_fence, STREAM_FLUSH_THRESHOLD, flush_output_text, flush_thinking_text
from app.models import GenerationJob, Module
from app.git_service import working_copy_path, ensure_repo, GitError

MAX_FIX_ROUNDS = 2
MVN_TIMEOUT = 300
NS = {"m": "http://maven.apache.org/POM/4.0.0"}


class ApiFileItem(BaseModel):
    path: str = Field(pattern=r"^src/test/(java|resources)/.+$")
    content: str = Field(min_length=1)


class ApiFilesPayload(BaseModel):
    files: list[ApiFileItem]


class MvnResult(BaseModel):
    success: bool
    output: str


def parse_api_files(text: str) -> ApiFilesPayload:
    """解析 AI 输出并归一化后做 pydantic 校验。

    与 pipeline._parse_staged_payload 同构:结构化输出端点不强制 schema 时模型会
    输出围栏 + 顶层数组(2026-08-17 E2E 实测),解析层兜底归一化为 {"files": [...]}。
    """
    import json
    data = json.loads(_strip_code_fence(text))
    if isinstance(data, list):
        data = {"files": data}
    return ApiFilesPayload.model_validate(data)


def _is_tracked(wc: Path, path: str) -> bool:
    r = subprocess.run(["git", "ls-files", "--", path], cwd=wc, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return bool(r.stdout.strip())


def write_files(wc: Path, files: list[dict], ai_owned: set[str] = frozenset()) -> list[dict]:
    """AI 产物写盘。

    拒绝越界/.git/覆盖用户手写的已跟踪文件;ai_owned(本项目历史 api_generation
    任务的 artifacts 路径)中的文件即使已推送变为已跟踪,也允许覆盖——否则
    生成→推送→再生成的迭代闭环会被"拒绝覆盖已跟踪文件"卡死(job#11 实测)。
    """
    result = []
    for f in files:
        path = f["path"]
        full = (wc / path).resolve()
        try:
            full.relative_to(wc.resolve())
        except ValueError:
            raise GitError("path", f"路径越界:{path}")
        if ".git" in Path(path).parts:
            raise GitError("path", f"禁止写入 .git:{path}")
        action = "overwritten" if full.exists() else "created"
        if _is_tracked(wc, path) and path not in ai_owned:
            raise GitError("path", f"拒绝覆盖已跟踪文件:{path}")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(f["content"], encoding="utf-8", newline="\n")
        result.append({"path": path, "action": action})
    return result


def _ai_owned_paths(db, project_id: int) -> set[str]:
    """聚合本项目历史 api_generation 任务写过的文件路径(artifacts)。

    用于 write_files 的 ai_owned 判定:AI 自己生成过的文件允许再次生成覆盖。
    """
    rows = (
        db.query(GenerationJob.artifacts)
        .filter(
            GenerationJob.project_id == project_id,
            GenerationJob.job_type == "api_generation",
            GenerationJob.artifacts.isnot(None),
        )
        .all()
    )
    owned: set[str] = set()
    for (artifacts,) in rows:
        for item in artifacts or []:
            if isinstance(item, dict) and item.get("path"):
                owned.add(item["path"])
    return owned


def _decode_mvn(b: bytes) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def run_mvn_compile(wc: Path) -> MvnResult:
    # Windows 下 mvn 是 .cmd 批处理,且 Maven bin 同时含无扩展名 Unix sh 脚本 "mvn",
    # shutil.which("mvn") 会先命中后者导致 WinError 193;必须优先解析 mvn.cmd
    mvn_bin = shutil.which("mvn.cmd") or shutil.which("mvn")
    if mvn_bin is None:
        raise GitError("mvn", "Maven 不可用,请检查宿主机环境")
    try:
        r = subprocess.run([mvn_bin, "-q", "test-compile"], cwd=wc, capture_output=True, timeout=MVN_TIMEOUT)
    except subprocess.TimeoutExpired:
        return MvnResult(success=False, output="mvn test-compile 超时(>300s)")
    out = _decode_mvn(r.stdout) + _decode_mvn(r.stderr)
    return MvnResult(success=r.returncode == 0, output=out)


def collect_project_summary(wc: Path) -> dict:
    summary = {"group_id": None, "artifact_id": None, "has_rest_assured": False, "has_junit5": False, "has_hamcrest": False, "test_packages": [], "has_base_class": False}
    pom = wc / "pom.xml"
    if pom.exists():
        try:
            tree = ET.parse(pom)
            root = tree.getroot()
            # 处理 Maven 命名空间(可能有也可能无)
            def _find(tag):
                for el in root.iter():
                    if el.tag.split("}")[-1] == tag:
                        return el
                return None
            gid = _find("groupId")
            aid = _find("artifactId")
            if gid is not None and gid.text:
                summary["group_id"] = gid.text.strip()
            if aid is not None and aid.text:
                summary["artifact_id"] = aid.text.strip()
            deps_text = "\n".join((el.text or "") for el in root.iter() if el.tag.split("}")[-1] == "artifactId")
            summary["has_rest_assured"] = "rest-assured" in deps_text
            summary["has_junit5"] = "junit-jupiter" in deps_text
            summary["has_hamcrest"] = "hamcrest" in deps_text
        except ET.ParseError:
            pass
    test_java = wc / "src/test/java"
    packages = set()
    base_found = False
    if test_java.exists():
        for p in test_java.rglob("*.java"):
            rel = p.relative_to(test_java).parent.as_posix()
            if rel and rel != ".":
                packages.add(rel)
            if "BaseApiTest" in p.name or p.name.endswith("BaseTest.java"):
                base_found = True
    summary["test_packages"] = sorted([pkg.replace("/", ".") for pkg in packages])
    summary["has_base_class"] = base_found
    return summary


async def process_api_job(job_id: int) -> None:
    """接口生成核心 handler。供 pipeline.process_job 按 job_type 分发调用。"""
    db = SessionLocal()
    try:
        stream_buf: list[str] = []  # 跨轮+异常路径共用
        thinking_buf: list[str] = []
        job = db.get(GenerationJob, job_id)
        if job is None:
            return
        project = job.project
        module = db.get(Module, job.target_module_id)
        module_name = module.name if module else "(未指定)"

        # bus.publish 闭包绑定 job_id(覆盖 _ai_generate 里的占位 0)
        async def publish(event):
            await bus.publish(job_id, event)

        job.status = "running"
        job.started_at = datetime.now()
        job.model = settings.ai_model
        db.commit()
        await publish({"type": "status", "status": "running"})

        # 读文档
        content = Path(job.document.storage_path).read_text(encoding="utf-8")

        # ensure working copy(自动兜底 clone)
        ensure_repo(project)
        wc = working_copy_path(project)
        summary = collect_project_summary(wc)

        # AI 生成(第 0 轮)
        chunks: list[str] = []
        async for kind, value in stream_api_generation(project.name, module_name, content, summary):
            if kind == "thinking":
                thinking_buf.append(value)
                await publish({"type": "thinking_delta", "text": value})
                if sum(len(s) for s in thinking_buf) >= STREAM_FLUSH_THRESHOLD:
                    flush_thinking_text(db, job_id, thinking_buf)
            elif kind == "delta":
                chunks.append(value)
                stream_buf.append(value)
                await publish({"type": "delta", "text": value})
                if sum(len(s) for s in stream_buf) >= STREAM_FLUSH_THRESHOLD:
                    flush_output_text(db, job_id, stream_buf)
            elif kind == "usage":
                in_t, out_t = value
                # 累计,不再覆盖;ORM 侧 None 先归零(column default 在 DB 层)
                job.input_tokens = (job.input_tokens or 0) + in_t
                job.output_tokens = (job.output_tokens or 0) + out_t
                job.cost_usd = estimate_cost(job.model, job.input_tokens, job.output_tokens)
                db.commit()

        artifacts: list[dict] = []
        last_error: str | None = None
        written_by_path: dict[str, str] = {}  # 跨修复轮累计(修复轮只重写部分文件)

        # AI 历史产物集合:这些文件即使推送后已跟踪也允许覆盖(再生成迭代)
        ai_owned = _ai_owned_paths(db, project.id)
        for round_idx in range(MAX_FIX_ROUNDS + 1):  # 0,1,2 = 初始 + 2 修复
            payload = parse_api_files("".join(chunks))
            artifacts = write_files(wc, [f.model_dump() for f in payload.files], ai_owned=ai_owned)
            for item in artifacts:
                written_by_path[item["path"]] = item["action"]
            # 写盘即落库:失败任务也保留产物清单,保证 ai_owned 数据源完备(job#12 实测)
            job.artifacts = [{"path": p, "action": a} for p, a in written_by_path.items()]
            db.commit()
            await publish({"type": "stage", "stage": "compiling"})
            mvn = run_mvn_compile(wc)
            if mvn.success:
                break
            last_error = mvn.output
            if round_idx == MAX_FIX_ROUNDS:
                break
            # 修复轮
            await publish({"type": "stage", "stage": "fixing", "round": round_idx + 1})
            flush_output_text(db, job_id, stream_buf)
            stream_buf.append("\n\n===== 修复轮 %d =====\n\n" % (round_idx + 1))
            flush_output_text(db, job_id, stream_buf)
            flush_thinking_text(db, job_id, thinking_buf)
            thinking_buf.append("\n\n===== 修复轮 %d =====\n\n" % (round_idx + 1))
            flush_thinking_text(db, job_id, thinking_buf)
            fix_prompt_extra = f"\n## 上次编译失败,错误如下(尾部)\n{mvn.output[-6000:]}\n本次写的文件:{[a['path'] for a in artifacts]}\n请只输出需要修改的文件,path 必须与原文件一致。"
            # 把修复提示拼进新一轮 AI 调用(复用 stream_api_generation,在文档后追加)
            chunks = []
            async for kind, value in stream_api_generation(project.name, module_name, content + fix_prompt_extra, summary):
                if kind == "thinking":
                    thinking_buf.append(value)
                    await publish({"type": "thinking_delta", "text": value})
                    if sum(len(s) for s in thinking_buf) >= STREAM_FLUSH_THRESHOLD:
                        flush_thinking_text(db, job_id, thinking_buf)
                elif kind == "delta":
                    chunks.append(value)
                    stream_buf.append(value)
                    await publish({"type": "delta", "text": value})
                    if sum(len(s) for s in stream_buf) >= STREAM_FLUSH_THRESHOLD:
                        flush_output_text(db, job_id, stream_buf)
                elif kind == "usage":
                    in_t, out_t = value
                    # 累计,不再覆盖;ORM 侧 None 先归零(column default 在 DB 层)
                    job.input_tokens = (job.input_tokens or 0) + in_t
                    job.output_tokens = (job.output_tokens or 0) + out_t
                    job.cost_usd = estimate_cost(job.model, job.input_tokens, job.output_tokens)
                    db.commit()

        job.artifacts = [{"path": p, "action": a} for p, a in written_by_path.items()]
        artifacts = job.artifacts

        if not mvn.success:
            job.status = "failed"
            job.error = (last_error or "mvn 失败")[-2000:]
            job.finished_at = datetime.now()
            flush_output_text(db, job_id, stream_buf)
            flush_thinking_text(db, job_id, thinking_buf)
            db.commit()
            await publish({"type": "error", "message": (last_error or "mvn 失败")[:500]})
            return

        job.status = "completed"
        job.finished_at = datetime.now()
        flush_output_text(db, job_id, stream_buf)
        flush_thinking_text(db, job_id, thinking_buf)
        db.commit()
        await publish({"type": "done", "files_count": len(artifacts)})

    except Exception as exc:
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error = str(exc)[:2000]
            job.finished_at = datetime.now()
            flush_output_text(db, job_id, stream_buf)
            flush_thinking_text(db, job_id, thinking_buf)
            db.commit()
        await bus.publish(job_id, {"type": "error", "message": str(exc)[:500]})
    finally:
        db.close()
