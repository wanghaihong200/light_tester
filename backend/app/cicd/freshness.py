"""新鲜度检测(ADR-0012 决策 4):平台工作区(执行分支)vs 远端对应分支。

只比对同步状态、只提示不阻塞;触发流程先 sync_repo(切到计划分支+reset)再检测,
因此 on_branch 恒真,dirty 信号主要来自未推送产物(untracked)——这正是「仓里有新代码
未同步」的形态。repo 参数为 AutomationRepo 行(鸭子类型兼容 git_service)。
"""
from app import git_service


def check_freshness(repo, branch: str) -> dict:
    wc = git_service.ensure_repo(repo)
    on_branch = git_service._current_branch(wc) == branch
    dirty = ahead = 0
    if on_branch:
        dirty = len(git_service.git_status(repo))
        try:
            ahead = int(git_service._run(
                ["git", "rev-list", "--count", f"origin/{branch}..HEAD"], cwd=wc).strip() or 0)
        except git_service.GitError:
            ahead = 0
    return {"on_branch": on_branch, "dirty_files": dirty, "ahead": ahead,
            "stale": bool(on_branch and (dirty > 0 or ahead > 0))}
