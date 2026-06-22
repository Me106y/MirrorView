import os
import socket
import subprocess
import sys
import time
import webbrowser
from getpass import getpass
from pathlib import Path
from threading import Thread
from typing import Dict, List, Optional


def _resolve_runtime_root() -> Path:
    explicit = (os.environ.get("MIRRORVIEW_ROOT") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parents[1]


ROOT = _resolve_runtime_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from client.core.api_client import APIClient

DEFAULT_API_BASE_URL = "http://127.0.0.1:5001/api"

LOGO_CMD = [
    "npx",
    "oh-my-logo",
    "MirrorView",
    "purple",
    "--filled",
    "--block-font",
    "block",
]

EXPERIENCE_OPTIONS = [
    "No experience",
    "1-2 years",
    "3-5 years",
    "5+ years",
]


class LocalBackendSupervisor:
    def __init__(self, root: Path, port: int = 5001):
        self.root = root
        self.port = port
        self.proc: Optional[subprocess.Popen] = None
        self.server_thread: Optional[Thread] = None
        self.server_handle = None
        self.in_process_server = False
        self.external_server = False

    def start(self) -> None:
        if self._is_port_open(self.port):
            self.external_server = True
            return

        env = self.build_runtime_env()
        should_inprocess = bool(getattr(sys, "frozen", False) or os.environ.get("MIRRORVIEW_TUI_INPROC_SERVER") == "1")
        if should_inprocess:
            self._start_in_process_server(env)
            return

        log_dir = self.root / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "tui_server.log"

        cmd = [sys.executable, str(self.root / "server" / "app.py")]
        with open(log_path, "a", encoding="utf-8") as log_file:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(self.root),
                env=env,
                stdout=log_file,
                stderr=log_file,
            )

        deadline = time.time() + 20
        while time.time() < deadline:
            if self._is_port_open(self.port):
                return
            if self.proc and self.proc.poll() is not None:
                raise RuntimeError("本地后端启动失败，请查看 log/tui_server.log")
            time.sleep(0.4)

        raise RuntimeError("本地后端启动超时，请查看 log/tui_server.log")

    def stop(self) -> None:
        if self.external_server:
            return
        if self.in_process_server:
            self._stop_in_process_server()
            return
        if not self.proc:
            return

        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)

        self.proc = None

    def build_runtime_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        data_dir = self._default_data_dir()
        env["PYTHONPATH"] = str(self.root) + os.pathsep + env.get("PYTHONPATH", "")
        env.setdefault("MIRRORVIEW_DATA_DIR", data_dir)
        env.setdefault("MIRRORVIEW_DB_PATH", str(Path(data_dir) / "mirrorview.db"))
        env.setdefault("MIRRORVIEW_RESUME_UPLOAD_FOLDER", str(Path(data_dir) / "uploads" / "resumes"))
        env.setdefault("MIRRORVIEW_CHROMA_DB_DIR", str(Path(data_dir) / "chroma_db"))
        self._load_env_files(env)
        return env

    def _default_data_dir(self) -> str:
        explicit_dir = (os.environ.get("MIRRORVIEW_DATA_DIR") or "").strip()
        if explicit_dir:
            Path(explicit_dir).expanduser().mkdir(parents=True, exist_ok=True)
            return str(Path(explicit_dir).expanduser())

        explicit = (os.environ.get("MIRRORVIEW_DB_PATH") or "").strip()
        if explicit:
            return str(Path(explicit).expanduser().resolve().parent)
        if getattr(sys, "frozen", False):
            home_data = Path.home() / ".mirrorview-tui" / "data"
            home_data.mkdir(parents=True, exist_ok=True)
            return str(home_data)
        local_data = self.root / "server" / "instance"
        local_data.mkdir(parents=True, exist_ok=True)
        return str(local_data)

    def _candidate_env_files(self) -> List[Path]:
        candidates: List[Path] = []
        for base in (self.root, Path.cwd(), Path(sys.executable).resolve().parent, Path.home() / ".mirrorview-tui"):
            for name in (".env_tts", ".env"):
                candidates.append(base / name)
        seen = set()
        unique: List[Path] = []
        for path in candidates:
            key = str(path.resolve()) if path.exists() else str(path)
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return unique

    def _load_env_files(self, env: Dict[str, str]) -> None:
        for path in self._candidate_env_files():
            if not path.exists() or not path.is_file():
                continue
            try:
                for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[len("export ") :].strip()
                    if "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and val and not env.get(key):
                        env[key] = val
            except Exception:
                continue

    def _start_in_process_server(self, env: Dict[str, str]) -> None:
        for key, val in env.items():
            if key and val and not os.environ.get(key):
                os.environ[key] = val

        from server.app import create_app
        from werkzeug.serving import make_server

        app = create_app()
        self.server_handle = make_server("127.0.0.1", self.port, app, threaded=True)

        self.server_thread = Thread(
            target=self.server_handle.serve_forever,
            name="mirrorview-inprocess-server",
            daemon=True,
        )
        self.server_thread.start()
        self.in_process_server = True

        deadline = time.time() + 20
        while time.time() < deadline:
            if self._is_port_open(self.port):
                return
            time.sleep(0.3)
        raise RuntimeError("本地后端启动超时（in-process 模式）。")

    def _stop_in_process_server(self) -> None:
        if self.server_handle is not None:
            try:
                self.server_handle.shutdown()
            except Exception:
                pass
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=3)
        self.server_thread = None
        self.server_handle = None
        self.in_process_server = False

    @staticmethod
    def _is_port_open(port: int) -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.3)
        try:
            return sock.connect_ex(("127.0.0.1", port)) == 0
        finally:
            sock.close()


class MirrorViewTUI:
    def __init__(self) -> None:
        base_url = (os.environ.get("MIRRORVIEW_API_BASE_URL") or "").strip() or DEFAULT_API_BASE_URL
        self.api_client = APIClient(base_url=base_url)
        self.user_data: Optional[Dict] = None
        self.history: List[Dict[str, str]] = []
        self.backend = LocalBackendSupervisor(ROOT)

    def run(self) -> None:
        self._show_logo()
        if not self._ensure_api_key():
            return

        try:
            self.backend.start()
        except Exception as e:
            print(f"\n[警告] 本地后端自动启动失败：{e}")
            if self.backend._is_port_open(self.backend.port):
                print("检测到已有可用后端，将继续使用。")
            else:
                print("未检测到可用后端，会话已终止。请修复后重试。")
                return

        print("\n欢迎使用 MirrorView")
        print("输入 /help 查看命令。首次建议输入 /login 或 /register。")

        try:
            while True:
                try:
                    user_text = input("\nyou> ").strip()
                except EOFError:
                    print("\n检测到 EOF，正在退出。")
                    break

                if not user_text:
                    continue

                if user_text.lower() in {"exit", "quit"}:
                    user_text = "/exit"

                lowered = user_text.lower()
                if lowered in {"/profile", "/me"}:
                    self._show_profile_flow()
                    continue
                if lowered in {"/edit-profile", "/edit_profile", "/update-profile", "/update_profile"}:
                    self._edit_profile_flow()
                    continue

                ok, payload = self.api_client.chat_careerforge_agent(
                    message=user_text,
                    history=self.history[-40:],
                )
                if not ok:
                    print(f"\nassistant> 请求失败：{payload}")
                    continue

                reply = (payload.get("reply") or "").strip()
                if reply:
                    print(f"\nassistant> {reply}")

                self.history.append({"role": "user", "content": user_text})
                if reply:
                    self.history.append({"role": "assistant", "content": reply})

                should_exit = self._handle_action(payload)
                self._handle_artifacts(payload)
                if should_exit:
                    break

        finally:
            self.backend.stop()
            print("\nMirrorView TUI 已退出。")

    def _ensure_api_key(self) -> bool:
        env = self.backend.build_runtime_env()
        api_key = (env.get("DEEPSEEK_API_KEY") or "").strip()
        if api_key:
            return True

        print("\n[错误] 未检测到 DEEPSEEK_API_KEY，无法启动有效会话。")
        print("请在以下任一文件中配置后重试：")
        for p in self.backend._candidate_env_files()[:6]:
            print(f"- {p}")
        print('示例：DEEPSEEK_API_KEY="sk-xxxx"')
        return False

    def _handle_action(self, payload: Dict) -> bool:
        action = (payload.get("action") or "").strip()

        if action == "client_auth_login":
            self._login_flow()
            return False

        if action == "client_auth_register":
            self._register_flow()
            return False

        if action == "client_logout":
            self.user_data = None
            self.api_client.user_id = None
            self.api_client.username = None
            self.history.clear()
            print("assistant> 当前会话已清空。")
            return False

        if action == "client_edit_profile":
            self._edit_profile_flow()
            return False

        if action == "start_mock_interview":
            self._run_text_interview_session()
            return False

        if action == "exit_app":
            return True

        return False

    def _handle_artifacts(self, payload: Dict) -> None:
        artifacts = payload.get("artifacts") or []
        if not isinstance(artifacts, list):
            return

        for item in artifacts:
            if not isinstance(item, dict):
                continue
            raw_path = (item.get("path") or "").strip()
            if not raw_path:
                continue
            title = (item.get("title") or "生成产物").strip()
            try:
                path = Path(raw_path)
                self.render_artifact(path, title=title)
            except Exception as e:
                print(f"assistant> 产物展示失败：{e}")

    def _run_text_interview_session(self) -> None:
        print("\nassistant> 正在创建文字模拟面试会话...")

        success, response = self.api_client.create_interview()
        if not success:
            msg = str(response)
            if "ongoing interview" in msg.lower():
                print("assistant> 检测到已有进行中的面试，尝试继续中...")
                rejoined = self._rejoin_active_interview()
                if not rejoined:
                    return
                response = rejoined
            else:
                print(f"assistant> 创建面试失败：{response}")
                return

        interview_id = response.get("interview_id")
        if not interview_id:
            print("assistant> 创建失败：缺少 interview_id")
            return

        initial_message = response.get("initial_message") or "面试已开始。"
        print(f"\nAI 面试官> {initial_message}")
        print("输入回答继续；输入 /end 结束并生成反馈；输入 /quit 返回主对话。")

        while True:
            text = input("interview> ").strip()
            if not text:
                continue

            lowered = text.lower()
            if lowered in {"/quit", "quit", "退出"}:
                print("assistant> 已返回主对话。")
                return

            if lowered in {"/end", "end", "结束", "/结束"}:
                finished, finish_resp = self.api_client.finish_interview(interview_id)
                if finished:
                    print("\nassistant> 面试已结束，反馈如下：\n")
                    print(finish_resp.get("feedback", ""))
                else:
                    print(f"assistant> 结束失败：{finish_resp}")
                return

            sent, ai_resp = self.api_client.send_message(interview_id, text, stream=False)
            if not sent:
                print(f"assistant> 发送失败：{ai_resp}")
                continue

            if isinstance(ai_resp, dict):
                content = ai_resp.get("response") or ai_resp.get("content") or str(ai_resp)
            else:
                content = str(ai_resp)
            print(f"\nAI 面试官> {content}")

    def _rejoin_active_interview(self) -> Optional[Dict]:
        ok, history = self.api_client.get_interview_history()
        if not ok:
            print(f"assistant> 查询历史失败：{history}")
            return None

        active = None
        for item in history or []:
            if int(item.get("status", 0)) == 1:
                active = item
                break

        if not active:
            print("assistant> 没有可继续的进行中面试。")
            return None

        interview_id = active.get("id")
        if not interview_id:
            return None

        rejoin_ok, payload = self.api_client.rejoin_interview(interview_id)
        if not rejoin_ok:
            print(f"assistant> 继续面试失败：{payload}")
            return None
        return payload

    def _login_flow(self) -> None:
        username = input("用户名: ").strip()
        password = getpass("密码: ").strip()
        if not username or not password:
            print("assistant> 用户名和密码不能为空。")
            return

        ok, data = self.api_client.login(username, password)
        if not ok:
            print(f"assistant> 登录失败：{data}")
            return

        self.user_data = data
        print(f"assistant> 登录成功，欢迎你，{data.get('username', username)}。")
        print("assistant> 你可以这样开始：")
        print("  - 输入 /help 查看全部命令")
        print("  - 输入 /profile 查看资料，/edit-profile 修改资料")
        if data.get("has_resume"):
            print("  - 检测到你已上传简历，可直接输入 /resume-match，然后补充岗位 JD")
            print("  - 也可以直接说：我想做简历匹配分析")
        else:
            print("  - 你还未上传简历，可先上传后再分析")
            print("  - 或直接在聊天里粘贴：简历内容: ...")
        print("  - 随时输入 /exit 退出")

    def _register_flow(self) -> None:
        username = input("用户名: ").strip()
        if not username:
            print("assistant> 用户名不能为空。")
            return

        password = getpass("密码: ").strip()
        confirm = getpass("确认密码: ").strip()
        if not password:
            print("assistant> 密码不能为空。")
            return
        if password != confirm:
            print("assistant> 两次密码不一致。")
            return

        role = input("求职意向（可选）: ").strip()

        print("工作经验选项:")
        for idx, item in enumerate(EXPERIENCE_OPTIONS, start=1):
            print(f"{idx}. {item}")
        exp_choice = input("请选择经验 (默认 1): ").strip()
        try:
            exp_idx = int(exp_choice) if exp_choice else 1
            exp = EXPERIENCE_OPTIONS[max(1, min(len(EXPERIENCE_OPTIONS), exp_idx)) - 1]
        except ValueError:
            exp = EXPERIENCE_OPTIONS[0]

        ok, data = self.api_client.register(username, password, role, exp)
        if ok:
            print("assistant> 注册成功。现在可输入 /login 登录。")
        else:
            print(f"assistant> 注册失败：{data}")

    def _edit_profile_flow(self) -> None:
        if not self.api_client.user_id:
            print("assistant> 你还没有登录，请先输入 /login。")
            return

        ok, profile = self.api_client.get_profile()
        if not ok or not isinstance(profile, dict):
            print(f"assistant> 读取资料失败：{profile}")
            return

        current_role = (profile.get("target_role") or "").strip()
        current_jd = (profile.get("target_jd") or "").strip()
        current_exp = (profile.get("work_experience") or "").strip()

        print("\nassistant> 进入资料编辑。留空则保持当前值。")
        print(f"- 当前目标岗位: {current_role or '未设置'}")
        print(f"- 当前工作经验: {current_exp or '未设置'}")
        print(f"- 当前目标JD: {(current_jd[:100] + '...') if len(current_jd) > 100 else (current_jd or '未设置')}")

        new_role = input(f"目标岗位 [{current_role or '未设置'}]: ").strip() or current_role
        new_jd = input("目标 JD（可粘贴一行文本，留空保持不变）: ").strip() or current_jd

        print("工作经验选项:")
        for idx, item in enumerate(EXPERIENCE_OPTIONS, start=1):
            print(f"{idx}. {item}")
        exp_prompt = f"工作经验 [{current_exp or EXPERIENCE_OPTIONS[0]}] (可输入编号或文本): "
        exp_input = input(exp_prompt).strip()
        if not exp_input:
            new_exp = current_exp or EXPERIENCE_OPTIONS[0]
        else:
            try:
                exp_idx = int(exp_input)
                new_exp = EXPERIENCE_OPTIONS[max(1, min(len(EXPERIENCE_OPTIONS), exp_idx)) - 1]
            except ValueError:
                new_exp = exp_input

        ok, result = self.api_client.update_profile(new_role, new_jd, new_exp)
        if not ok:
            print(f"assistant> 保存失败：{result}")
            return

        print("assistant> 资料已更新。")
        reloaded_ok, latest = self.api_client.get_profile()
        if reloaded_ok and isinstance(latest, dict):
            role = (latest.get("target_role") or "").strip() or "未设置"
            exp = (latest.get("work_experience") or "").strip() or "未设置"
            print(f"assistant> 最新资料：目标岗位={role}，工作经验={exp}")

    def _show_profile_flow(self) -> None:
        if not self.api_client.user_id:
            print("assistant> 你还没有登录，请先输入 /login。")
            return

        ok, profile = self.api_client.get_profile()
        if not ok or not isinstance(profile, dict):
            print(f"assistant> 读取资料失败：{profile}")
            return

        role = (profile.get("target_role") or "").strip() or "未设置"
        exp = (profile.get("work_experience") or "").strip() or "未设置"
        jd = (profile.get("target_jd") or "").strip()
        jd_preview = (jd[:120] + "...") if len(jd) > 120 else (jd or "未设置")
        has_resume = "是" if profile.get("has_resume") else "否"

        print("\nassistant> 当前资料：")
        print(f"- 用户名: {(profile.get('username') or '').strip() or '未知'}")
        print(f"- 目标岗位: {role}")
        print(f"- 工作经验: {exp}")
        print(f"- 目标JD: {jd_preview}")
        print(f"- 已上传简历: {has_resume}")
        print("assistant> 如需修改，请输入 /edit-profile。")

    def render_artifact(self, path: Path, title: str = "生成产物") -> None:
        abs_path = path.expanduser().resolve()
        file_uri = abs_path.as_uri()
        clickable_uri = self._osc8_link(file_uri, file_uri)

        print("\n" + "=" * 72)
        print(title)
        print("=" * 72)
        print(f"绝对路径: {abs_path}")
        print(f"file URL: {file_uri}")
        print(f"可点击链接: {clickable_uri}")
        print("操作: [O] 打开浏览器  [C] 复制路径  [Enter] 返回")

        while True:
            cmd = input("> ").strip().lower()
            if not cmd:
                return
            if cmd == "o":
                try:
                    opened = webbrowser.open(file_uri)
                    if opened:
                        print("已请求默认浏览器打开。")
                    else:
                        print("浏览器打开请求已发送，请手动确认。")
                except Exception as exc:
                    print(f"打开失败: {exc}")
                continue
            if cmd == "c":
                if self._copy_to_clipboard(str(abs_path)):
                    print("路径已复制到剪贴板。")
                else:
                    print("复制失败，当前终端不支持自动复制。")
                continue
            print("无效指令，请输入 O / C / Enter。")

    def _show_logo(self) -> None:
        print("\n正在加载 MirrorView ...\n")
        try:
            subprocess.run(LOGO_CMD, cwd=str(ROOT), check=True, timeout=12)
        except FileNotFoundError:
            print("MirrorView")
            print("提示: 未检测到 npx，已跳过 logo。")
        except subprocess.TimeoutExpired:
            print("MirrorView")
            print("提示: logo 命令执行超时，已跳过。")
        except subprocess.CalledProcessError as exc:
            print("MirrorView")
            print(f"提示: logo 命令执行失败，已跳过。({exc})")
        print("\nMirrorView TUI 已启动。")

    @staticmethod
    def _osc8_link(url: str, label: str) -> str:
        if not sys.stdout.isatty() or os.environ.get("TERM", "").lower() == "dumb":
            return url
        return f"\033]8;;{url}\033\\{label}\033]8;;\033\\"

    @staticmethod
    def _copy_to_clipboard(text: str) -> bool:
        try:
            if sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
                return True
            if os.name == "nt":
                subprocess.run("clip", input=text.encode("utf-16le"), check=True, shell=True)
                return True

            for cmd in (
                ["wl-copy"],
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ):
                try:
                    subprocess.run(cmd, input=text.encode("utf-8"), check=True)
                    return True
                except Exception:
                    continue
        except Exception:
            return False
        return False


def main() -> None:
    app = MirrorViewTUI()
    app.run()


if __name__ == "__main__":
    main()
