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
from app.jobs.pipeline import _strip_code_fence
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


def write_files(wc: Path, files: list[dict]) -> list[dict]:
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
        if _is_tracked(wc, path):
            raise GitError("path", f"拒绝覆盖已跟踪文件:{path}")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(f["content"], encoding="utf-8", newline="\n")
        result.append({"path": path, "action": action})
    return result


def _decode_mvn(b: bytes) -> str:
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def run_mvn_compile(wc: Path) -> MvnResult:
    # Windows 下 mvn 是 .cmd 批处理,subprocess 不经 shell 直调 "mvn" 会 FileNotFoundError,
    # 必须用 shutil.which 按 PATHEXT 解析全路径(E2E 实测缺陷)
    mvn_bin = shutil.which("mvn")
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
        job = db.get(GenerationJob, job_id)
        if job is None:
            return
        project = job.project
        module = db.get(Module, job.target_module_id)

        # bus.publish 闭包绑定 job_id(覆盖 _ai_generate 里的占位 0)
        async def publish(event):
            await bus.publish(job_id, event)

        job.status = "running"
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
        in_tok = out_tok = 0
        async for kind, value in stream_api_generation(project.name, module.name, content, summary):
            if kind == "delta":
                chunks.append(value)
                await publish({"type": "delta", "text": value})
            elif kind == "usage":
                in_tok, out_tok = value

        artifacts: list[dict] = []
        last_error: str | None = None

        for round_idx in range(MAX_FIX_ROUNDS + 1):  # 0,1,2 = 初始 + 2 修复
            payload = parse_api_files("".join(chunks))
            artifacts = write_files(wc, [f.model_dump() for f in payload.files])
            await publish({"type": "stage", "stage": "compiling"})
            mvn = run_mvn_compile(wc)
            if mvn.success:
                break
            last_error = mvn.output
            if round_idx == MAX_FIX_ROUNDS:
                break
            # 修复轮
            await publish({"type": "stage", "stage": "fixing", "round": round_idx + 1})
            fix_prompt_extra = f"\n## 上次编译失败,错误如下(尾部)\n{mvn.output[-6000:]}\n本次写的文件:{[a['path'] for a in artifacts]}\n请只输出需要修改的文件,path 必须与原文件一致。"
            # 把修复提示拼进新一轮 AI 调用(复用 stream_api_generation,在文档后追加)
            chunks = []
            async for kind, value in stream_api_generation(project.name, module.name, content + fix_prompt_extra, summary):
                if kind == "delta":
                    chunks.append(value)
                    await publish({"type": "delta", "text": value})
                elif kind == "usage":
                    in_tok, out_tok = value

        job.input_tokens = in_tok
        job.output_tokens = out_tok
        job.cost_usd = estimate_cost(job.model, in_tok, out_tok)
        job.artifacts = artifacts

        if not mvn.success:
            job.status = "failed"
            job.error = (last_error or "mvn 失败")[-2000:]
            db.commit()
            await publish({"type": "error", "message": (last_error or "mvn 失败")[:500]})
            return

        job.status = "completed"
        db.commit()
        await publish({"type": "done", "files_count": len(artifacts)})

    except Exception as exc:
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error = str(exc)[:2000]
            db.commit()
        await bus.publish(job_id, {"type": "error", "message": str(exc)[:500]})
    finally:
        db.close()
