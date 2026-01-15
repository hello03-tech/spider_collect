import os
from loguru import logger
from dotenv import find_dotenv, load_dotenv
from xhs_utils.cookie_util import trans_cookies


def load_env():
    # Prefer loading the repo-root .env explicitly so it works regardless of CWD,
    # and avoid python-dotenv's stack-frame based discovery (can break on some runtimes).
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    env_path = os.path.join(repo_root, '.env')
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
    else:
        # Fallback: search from current working directory.
        load_dotenv(dotenv_path=find_dotenv(usecwd=True))
    cookies_str = os.getenv('COOKIES', '')
    if cookies_str:
        cookies_str = cookies_str.strip().replace('\n', '')
    return cookies_str

def init():
    media_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/media_datas'))
    excel_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/excel_datas'))
    json_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/json_datas'))
    for base_path in [media_base_path, excel_base_path, json_base_path]:
        if not os.path.exists(base_path):
            os.makedirs(base_path)
            logger.info(f'创建目录 {base_path}')
    cookies_str = load_env()
    if not cookies_str:
        raise RuntimeError(
            "COOKIES 未设置：请将 .env.example 复制为 .env，并把浏览器里登录后抓到的 Cookie 整串填到 COOKIES=...（必须包含 a1=...）。"
        )
    try:
        cookies = trans_cookies(cookies_str)
    except Exception as exc:
        raise RuntimeError(f"COOKIES 解析失败：{exc}。请确认 COOKIES 是浏览器复制的完整 Cookie 字符串。")
    if not cookies.get("a1"):
        raise RuntimeError(
            "COOKIES 缺少 a1：请确认你复制的是“已登录小红书”的 Cookie，并且 COOKIES 里包含 a1=...。"
        )
    base_path = {
        'media': media_base_path,
        'excel': excel_base_path,
        'json': json_base_path,
    }
    return cookies_str, base_path
