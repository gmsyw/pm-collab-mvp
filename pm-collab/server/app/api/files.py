"""文件预览/下载（证据文件等）。

安全约束：仅允许访问 `settings.data_dir` 之内的文件，禁止越界（../ 或绝对路径逃逸）。
前端通过 axios（携带 Bearer 与项目上下文）以 blob 方式拉取，再于 FilePreview 中渲染。
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import settings
from ..models import Member
from .deps import current_member

router = APIRouter(prefix="/api/files", tags=["文件"])


def _strip_to_data(p: Path, root: Path) -> Path | None:
    """跨机/跨目录迁移：截取绝对路径中最后一次出现的 data 目录之后的部分，重映射到当前 data_dir。

    例如库里存的是旧机器绝对路径 D:\\old\\...\\data\\projects\\PROJ\\x.md，
    安装到 D:\\PM-Collab 后 data_dir=D:\\PM-Collab\\data，重映射为 D:\\PM-Collab\\data\\projects\\PROJ\\x.md。
    """
    parts = p.resolve().parts
    for i in range(len(parts) - 1, -1, -1):
        if parts[i] == "data":
            return root.joinpath(*parts[i + 1:])
    return None


def _resolve(path: str) -> Path:
    root = settings.data_dir.resolve()
    p = Path(path)
    candidates: list[Path] = []
    if p.is_absolute():
        cand = p.resolve()
        candidates.append(cand)  # 原始绝对路径（仅当落在 data_dir 内才有效）
        # 跨目录迁移：把绝对路径重映射到当前 data_dir 后再尝试
        remapped = _strip_to_data(p, root)
        if remapped is not None:
            candidates.append(remapped)
    else:
        # 相对路径：剥离可能多余的 data/ 前缀（data_dir 本身已是 .../data），避免双重 data
        parts = list(p.parts)
        if parts and parts[0] in ("data", "data/"):
            p = Path(*parts[1:])
        candidates.append(root / p)
        # 兼容项目子目录布局（data/projects/<项目>/...）与旧版顶层布局
        try:
            proj_root = root / "projects"
            if proj_root.is_dir():
                for proj in proj_root.iterdir():
                    if proj.is_dir():
                        candidates.append(proj / p)
        except Exception:
            pass
    for c in candidates:
        cc = c.resolve()
        if (cc == root or root in cc.parents) and cc.is_file():
            return cc
    raise HTTPException(status_code=404, detail="文件不存在")


@router.get("/preview")
def preview(
    path: str = Query(..., description="相对于 data_dir 的文件路径"),
    _: Member = Depends(current_member),
) -> FileResponse:
    f = _resolve(path)
    return FileResponse(f)
