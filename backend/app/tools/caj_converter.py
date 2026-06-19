"""CAJ 格式转换模块 —— 将知网 .caj 文件转换为 PDF

使用 caj2pdf 工具（https://github.com/JeziL/caj2pdf）。
caj2pdf 是一个脚本工具，需要克隆到本地后通过 python 调用。
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# caj2pdf 默认查找路径
_CAJ2PDF_DIR = Path(__file__).parent.parent.parent / "tools" / "caj2pdf"


def _find_caj2pdf_script() -> Path | None:
    """查找 caj2pdf 脚本（无扩展名的 Python 脚本）"""
    # 1. 项目内 tools/caj2pdf/caj2pdf
    local_script = _CAJ2PDF_DIR / "caj2pdf"
    if local_script.exists():
        return local_script

    # 2. 兼容 .py 扩展名
    local_script_py = _CAJ2PDF_DIR / "caj2pdf.py"
    if local_script_py.exists():
        return local_script_py

    # 3. 环境变量 CAJ2PDF_PATH
    import os
    env_path = os.environ.get("CAJ2PDF_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
        if p.is_dir():
            for name in ["caj2pdf", "caj2pdf.py"]:
                script = p / name
                if script.exists():
                    return script

    return None


def is_caj_available() -> bool:
    """检查 caj2pdf 是否可用"""
    script = _find_caj2pdf_script()
    return script is not None


def convert_caj_to_pdf(caj_path: str | Path, output_dir: str | Path | None = None) -> str | None:
    """将 .caj 文件转换为 PDF

    Args:
        caj_path: .caj 文件路径
        output_dir: 输出目录，默认与 .caj 文件同目录

    Returns:
        转换后的 PDF 文件路径，失败返回 None
    """
    caj_path = Path(caj_path)
    if not caj_path.exists():
        logger.error(f"CAJ 文件不存在: {caj_path}")
        return None

    if not caj_path.suffix.lower() == ".caj":
        logger.error(f"不是 CAJ 文件: {caj_path}")
        return None

    # 确定输出路径
    if output_dir is None:
        output_dir = caj_path.parent
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = output_dir / f"{caj_path.stem}.pdf"

    # 如果已存在转换结果，直接返回
    if pdf_path.exists():
        logger.info(f"PDF 已存在，跳过转换: {pdf_path.name}")
        return str(pdf_path)

    # 查找 caj2pdf 脚本
    script = _find_caj2pdf_script()
    if not script:
        logger.error(
            f"CAJ 转换失败: caj2pdf 未安装\n"
            f"  请执行以下命令安装:\n"
            f"  cd backend/tools && git clone https://github.com/JeziL/caj2pdf.git"
        )
        return None

    # 调用 caj2pdf 转换
    try:
        logger.info(f"使用 caj2pdf 转换: {caj_path.name}")
        result = subprocess.run(
            ["python", str(script), "convert", str(caj_path), "-o", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(script.parent),  # 在 caj2pdf 目录下运行
        )

        if result.returncode == 0 and pdf_path.exists():
            logger.info(f"  转换成功: {pdf_path.name}")
            return str(pdf_path)
        else:
            error_msg = result.stderr.strip() or result.stdout.strip()
            logger.warning(f"caj2pdf 转换失败: {error_msg}")
            return None

    except subprocess.TimeoutExpired:
        logger.error(f"caj2pdf 转换超时: {caj_path.name}")
        return None
    except Exception as e:
        logger.error(f"caj2pdf 执行失败: {e}")
        return None
