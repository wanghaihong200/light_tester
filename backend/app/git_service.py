"""Git 服务层:subprocess 直调 git.exe。token 拼入 URL,绝不落日志。"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel

from app.config import settings


class GitError(Exception):
    def __init__(self, stage: str, message: str):
        self.stage = stage
        self.message = message
        super().__init__(f"[{stage}] {message}")


class SyncResult(BaseModel):
    cloned: bool = False
    updated: bool = False
    failed: bool = False
    branch: str = ""
    commit_short: str = ""
    error: str | None = None


class FileNode(BaseModel):
    name: str
    path: str
    is_dir: bool
    children: list["FileNode"] | None = None


class ChangeFile(BaseModel):
    path: str
    status: Literal["added", "modified", "deleted"]
    tracked: bool


_FILTER_DIRS = {".git", "target", ".idea", ".mvn", "node_modules"}
_TIMEOUT_DEFAULT = 30
_TIMEOUT_CLONE = 120


def working_copy_path(project) -> Path:
    # 必须归一为绝对路径(相对路径会二次拼接成 data/data/repos,E2E 实测缺陷)。
    # 带 kind 属性的形态是 AutomationRepo:按 (project_id, kind) 分目录,与 Project 的 repo_{id} 互不冲突。
    base = settings.repos_dir.resolve()
    kind = getattr(project, "kind", None)
    if kind:
        return base / f"repo_{project.project_id}_{kind}"
    return base / f"repo_{project.id}"


def validate_repo_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise GitError("url", "git_repo_url 必须是 http(s) 且 host 非空")


def _sanitize(text: str, token: str | None) -> str:
    if token:
        text = text.replace(token, "***")
    return text


def build_remote_url(project) -> str:
    """拼装访问远程仓库的 URL。

    内部使用,不落日志。scheme 分流:
    - file://  : 本地仓库(测试/本地),无需 token,原样返回。
    - http(s):// : 远程 GitLab,要求配置 git_token,token 拼入 userinfo。
    - 其他    : 抛 GitError(stage=url)。

    注:此处不复用 validate_repo_url,因其严格禁止 file 协议;在生产 API 入口
    (create_job,Task 6)会调用 validate_repo_url 强制 http(s)。本地 file://
    仅在测试 ensure_repo/sync_repo 路径出现。
    """
    url = project.git_repo_url or ""
    p = urlparse(url)
    scheme = p.scheme.lower()
    if scheme == "file":
        return url
    if scheme in ("http", "https"):
        if not p.netloc:
            raise GitError("url", "git_repo_url 必须是 http(s) 或 file 且 host 非空")
        if not project.git_token:
            raise GitError("auth", "项目未配置 git_token")
        return f"{p.scheme}://oauth2:{project.git_token}@{p.netloc}{p.path}"
    raise GitError("url", "git_repo_url 必须是 http(s) 或 file 且 host 非空")


def _run(args: list[str], cwd: Path, token: str | None = None, timeout: int = _TIMEOUT_DEFAULT) -> str:
    """跑 git 子进程,失败 raise GitError(stderr 脱敏)。"""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        raise GitError("git", "git 不可用,请检查宿主机环境")
    if r.returncode != 0:
        raise GitError(args[0] if args else "git", _sanitize(r.stderr or r.stdout, token))
    return r.stdout


def ensure_repo(project) -> Path:
    wc = working_copy_path(project)
    if wc.exists() and (wc / ".git").exists():
        return wc
    url = build_remote_url(project)
    wc.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "-q", url, str(wc)], cwd=wc.parent, token=project.git_token, timeout=_TIMEOUT_CLONE)
    return wc


def _current_branch(wc: Path) -> str:
    return _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=wc).strip()


def _switch_branch(wc: Path, project, branch: str) -> None:
    """切到远程已存在的分支(checkout -B 到 origin/<branch>)。远程没有则报错。"""
    out = _run(["git", "branch", "-r"], cwd=wc)
    remote_names = {ln.strip()[len("origin/"):] for ln in out.splitlines()
                    if ln.strip().startswith("origin/") and "->" not in ln}
    if branch not in remote_names:
        raise GitError("branch", f"远程不存在分支:{branch}")
    _run(["git", "checkout", "-q", "-B", branch, f"origin/{branch}"], cwd=wc)


def sync_repo(project, branch: str | None = None) -> SyncResult:
    """同步 working copy;branch 指定时先切到该远程分支(不存在则报错)。

    untracked 文件(AI 未推送产物)不受 reset --hard 影响,切分支后保留。
    """
    wc = working_copy_path(project)
    if not (wc.exists() and (wc / ".git").exists()):
        ensure_repo(project)
        if branch:
            _switch_branch(wc, project, branch)
        cur = _current_branch(wc)
        commit = _run(["git", "rev-parse", "--short", "HEAD"], cwd=wc).strip()
        return SyncResult(cloned=True, branch=cur, commit_short=commit)
    url = build_remote_url(project)
    # 显式 refspec:`git fetch <url>` 仅写 FETCH_HEAD,不更新 refs/remotes/origin/*;
    # 后续 reset --hard origin/<branch> 依赖 remote-tracking ref,故须显式映射。
    _run(["git", "fetch", "-q", url, "+refs/heads/*:refs/remotes/origin/*"], cwd=wc, token=project.git_token)
    if branch and branch != _current_branch(wc):
        _switch_branch(wc, project, branch)
    cur = _current_branch(wc)
    _run(["git", "reset", "--hard", "-q", f"origin/{cur}"], cwd=wc)
    commit = _run(["git", "rev-parse", "--short", "HEAD"], cwd=wc).strip()
    return SyncResult(updated=True, branch=cur, commit_short=commit)


def _repo_display_name(project, wc: Path) -> str:
    """文件树根节点显示名:取 git_repo_url 末段项目名(去 .git 后缀),
    与 GitLab 页面上的仓库名一致;URL 缺失/解析不出时回退本地目录名。"""
    path = urlparse(project.git_repo_url or "").path.rstrip("/")
    last = path.rsplit("/", 1)[-1] if path else ""
    if last.endswith(".git"):
        last = last[: -len(".git")]
    return last or wc.name


def list_files(project) -> FileNode:
    wc = working_copy_path(project)
    if not (wc.exists() and (wc / ".git").exists()):
        raise GitError("repo", "working copy 不存在,请先同步")

    def build(rel: Path) -> FileNode:
        full = wc / rel
        name = rel.name or _repo_display_name(project, wc)
        if full.is_dir():
            children = []
            for child in sorted(full.iterdir()):
                if child.name in _FILTER_DIRS:
                    continue
                children.append(build(rel / child.name))
            return FileNode(name=name, path=rel.as_posix(), is_dir=True, children=children)
        return FileNode(name=name, path=rel.as_posix(), is_dir=False, children=None)

    return build(Path(""))


def read_file(project, rel_path: str) -> str:
    wc = working_copy_path(project)
    full = (wc / rel_path).resolve()
    try:
        full.relative_to(wc.resolve())
    except ValueError:
        raise GitError("path", "路径越界")
    if ".git" in Path(rel_path).parts:
        raise GitError("path", "禁止访问 .git")
    if not full.exists() or not full.is_file():
        raise GitError("path", "文件不存在")
    data = full.read_bytes()
    if b"\x00" in data:
        raise GitError("path", "二进制文件不支持预览")
    return data.decode("utf-8", errors="replace")


def git_status(project) -> list[ChangeFile]:
    wc = working_copy_path(project)
    if not (wc.exists() and (wc / ".git").exists()):
        raise GitError("repo", "working copy 不存在,请先同步")
    result: list[ChangeFile] = []
    # 未跟踪:porcelain 会把整个目录折叠成 "dir/"(E2E 实测 src/、target/ 混入推送列表),
    # 改用 ls-files --others 展开到具体文件,并过滤构建产物目录(_FILTER_DIRS)
    others = _run(["git", "ls-files", "--others", "--exclude-standard"], cwd=wc)
    for path in others.splitlines():
        if not path:
            continue
        first = Path(path).parts[0] if Path(path).parts else ""
        if first in _FILTER_DIRS:
            continue
        result.append(ChangeFile(path=path, status="added", tracked=False))
    # 已跟踪变更:M/D/A(关闭未跟踪枚举,?? 分支已由上面处理)
    out = _run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=wc)
    for line in out.splitlines():
        if not line:
            continue
        xy, path = line[:2], line[3:]
        # porcelain v1: 两个状态码 XY;修改  M;删除  D;新增 A 等
        if "D" in xy:
            result.append(ChangeFile(path=path, status="deleted", tracked=True))
        elif "M" in xy or "A" in xy:
            result.append(ChangeFile(path=path, status="modified" if "M" in xy else "added", tracked=True))
    return result


def list_remote_branches(project) -> list[str]:
    wc = working_copy_path(project)
    if not (wc.exists() and (wc / ".git").exists()):
        raise GitError("repo", "working copy 不存在,请先同步")
    out = _run(["git", "branch", "-r"], cwd=wc)
    branches = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "->" in line:
            continue
        if line.startswith("origin/"):
            branches.append(line[len("origin/"):])
    return branches


def remote_branch_files(project, branch: str) -> set[str]:
    """分支上全部文件路径集合(物料感知用):fetch 刷新 remote-tracking refs 但不动工作区,
    再 ls-tree 枚举 origin/<branch>。分支不存在抛 GitError(由调用方转 400)。"""
    wc = working_copy_path(project)
    if not (wc.exists() and (wc / ".git").exists()):
        ensure_repo(project)
    url = build_remote_url(project)
    _run(["git", "fetch", "-q", url, "+refs/heads/*:refs/remotes/origin/*"], cwd=wc, token=project.git_token)
    out = _run(["git", "ls-tree", "-r", "--name-only", f"origin/{branch}"], cwd=wc, token=project.git_token)
    return {ln for ln in out.splitlines() if ln}


class PushConflict(GitError):
    def __init__(self, message: str):
        super().__init__("rebase", message)


class NothingToCommit(GitError):
    def __init__(self):
        super().__init__("nothing_to_commit", "没有变更可提交")


class PushResult(BaseModel):
    ok: bool
    branch: str
    commit_short: str
    pushed_files: list[str]


def push_files(project, files: list[str], branch: str, commit_msg: str) -> PushResult:
    wc = working_copy_path(project)
    if not (wc.exists() and (wc / ".git").exists()):
        raise GitError("repo", "working copy 不存在,请先同步")
    token = project.git_token
    # 路径越界校验
    for f in files:
        full = (wc / f).resolve()
        try:
            full.relative_to(wc.resolve())
        except ValueError:
            raise GitError("path", f"路径越界:{f}")
    if not files:
        raise NothingToCommit()
    # checkout 分支:本地有则切,无则从 origin 创建 track
    branches_out = _run(["git", "branch", "--list", branch], cwd=wc)
    if branches_out.strip():
        _run(["git", "checkout", "-q", branch], cwd=wc)
    else:
        # 远程是否有该分支
        remote_branches = list_remote_branches(project)
        if branch in remote_branches:
            _run(["git", "fetch", "-q", "origin", branch], cwd=wc, token=token)
            _run(["git", "checkout", "-q", "-B", branch, f"origin/{branch}"], cwd=wc)
        else:
            _run(["git", "checkout", "-q", "-b", branch], cwd=wc)
    # add + commit 先行:调用方(导出/AI 生成)在 push_files 之前已把文件写入工作区,
    # 若先 pull --rebase,改写已跟踪文件(再导出覆盖 RUN.md/重推 AI 产物)时工作区带
    # 未暂存变更,rebase 直接拒绝(exit 128),曾被他报成「与远程冲突」(2026-09-07 冒烟)。
    for f in files:
        _run(["git", "add", "--", f], cwd=wc)
    # 是否有暂存变更
    diff = _run(["git", "diff", "--cached", "--name-only"], cwd=wc)
    if not diff.strip():
        raise NothingToCommit()
    _run(["git", "commit", "-qm", commit_msg], cwd=wc)
    # pull --rebase(远程分支存在时):提交后工作区干净,rebase 才可执行;
    # 真冲突在此暴露(本地提交重放撞上远程同名文件改动),abort 回到本地分支态
    if branch in list_remote_branches(project):
        r = subprocess.run(["git", "pull", "-q", "--rebase", "origin", branch], cwd=wc, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            detail = (r.stderr or r.stdout or "").strip()
            # 连接类失败(GitLab 未启动/网络断)发生在 fetch 阶段,rebase 尚未开始;
            # 归 409「与远程冲突」会误导排障,单独归 stage=pull
            low = detail.lower()
            if any(sig in low for sig in ("failed to connect", "connection refused",
                                          "could not resolve host", "connection timed out")):
                raise GitError("pull", _sanitize(detail.splitlines()[0] if detail else "git pull 失败", token))
            subprocess.run(["git", "rebase", "--abort"], cwd=wc, capture_output=True)
            first_line = detail.splitlines()[0] if detail else ""
            raise PushConflict("与远程有冲突,请检查 API 文档或重试同步"
                               + (f"({first_line})" if first_line else ""))
    # rebase 可能改写提交哈希:取 pull 之后的 HEAD,保证上报的是实际推送的 commit
    commit_short = _run(["git", "rev-parse", "--short", "HEAD"], cwd=wc).strip()
    # push
    r = subprocess.run(["git", "push", "-q", "origin", branch], cwd=wc, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise GitError("push", _sanitize(r.stderr or r.stdout, token))
    return PushResult(ok=True, branch=branch, commit_short=commit_short, pushed_files=files)
