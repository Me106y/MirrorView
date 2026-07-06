import logging
import os
import re
import sys
from datetime import datetime
from utils.path_tool import get_abs_path


def _resolve_log_root():
    """
    Pick a writable log directory.
    - Local dev: prefer repo ./log
    - Serverless/read-only env (e.g., Vercel): fall back to /tmp
    """
    candidates = []

    env_log_dir = (os.environ.get("MIRRORVIEW_LOG_DIR") or "").strip()
    if env_log_dir:
        candidates.append(env_log_dir)

    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        candidates.append("/tmp/mirrorview-log")
    else:
        candidates.append(get_abs_path("log"))
        candidates.append("/tmp/mirrorview-log")

    for path in candidates:
        try:
            os.makedirs(path, exist_ok=True)
            if os.access(path, os.W_OK):
                return path
        except Exception:
            continue

    return None


# 日志保存的根目录（None 表示仅控制台）
LOG_ROOT = _resolve_log_root()

# 日志的格式配置
DEFAULT_LOG_FORMAT = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)

_SENSITIVE_REGEX = [
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(authorization\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(cookie\s*[:=]\s*)([^\s,;]+)"),
    re.compile(r"\b(sk-[A-Za-z0-9_\-]{8,})\b"),
    re.compile(r"\b(bai-[A-Za-z0-9_\-]{8,})\b"),
]


def _sanitize_text(text: str) -> str:
    masked = text
    for rgx in _SENSITIVE_REGEX:
        if rgx.pattern.startswith("(?i)("):
            masked = rgx.sub(r"\1***", masked)
        else:
            masked = rgx.sub("***", masked)
    return masked


def _sanitize_object(value):
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            k = str(key)
            if k.lower() in {"api_key", "authorization", "cookie", "token"}:
                safe[key] = "***"
            else:
                safe[key] = _sanitize_object(item)
        return safe
    if isinstance(value, (list, tuple)):
        t = [_sanitize_object(x) for x in value]
        return type(value)(t)
    return value


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = _sanitize_text(record.msg)
            elif record.msg is not None:
                record.msg = _sanitize_object(record.msg)

            if record.args:
                if isinstance(record.args, dict):
                    record.args = _sanitize_object(record.args)
                elif isinstance(record.args, tuple):
                    record.args = tuple(_sanitize_object(arg) for arg in record.args)
                else:
                    record.args = _sanitize_object(record.args)
        except Exception:
            # Never block logging due to sanitizer errors.
            pass
        return True

def get_logger(
        name: str = "agent",
        console_level: int = logging.INFO,  # 控制台默认只显示INFO及以上
        file_level: int = logging.DEBUG,
        log_file=None,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加Handler
    if logger.handlers:
        return logger

    # 控制台Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(DEFAULT_LOG_FORMAT)
    console_handler.addFilter(SensitiveDataFilter())
    logger.addHandler(console_handler)

    # 文件Handler（若目录不可写则自动跳过）
    if LOG_ROOT:
        if not log_file:
            log_file = os.path.join(LOG_ROOT, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(file_level)
            file_handler.setFormatter(DEFAULT_LOG_FORMAT)
            file_handler.addFilter(SensitiveDataFilter())
            logger.addHandler(file_handler)
        except Exception as e:
            print(f"[logger] file logging disabled: {e}", file=sys.stderr)

    return logger

# 快捷获取日志器
logger = get_logger()

if __name__ == '__main__':
    logger.info("信息日志")
    logger.error("错误日志")
    logger.warning("警告日志")
    logger.debug("调试日志")
