import base64
import json
import os
import time
from typing import Dict, List

import requests
from loguru import logger

CONFIG_LOADED = False


def _load_llm_config():
    global CONFIG_LOADED
    if CONFIG_LOADED:
        return
    config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config', '1.txt'))
    if not os.path.exists(config_path):
        logger.warning(f'llm config not found: {config_path}')
        return
    ctx = {'os': os}
    with open(config_path, encoding='utf-8') as f:
        exec(f.read(), ctx)
    CONFIG_LOADED = True


def _build_prompt(note: Dict, image_b64_list: List[str]) -> str:
    title = note.get('title', '无标题')
    desc = note.get('desc', '')
    tags = ', '.join(note.get('tags', []))
    meta = f"标题：{title}\n描述：{desc}\n标签：{tags}"
    preview_images = [img for img in image_b64_list if img][:2]
    images = '\n'.join(
        f"图片{i + 1}base64:{image_b64}" for i, image_b64 in enumerate(preview_images) if image_b64)
    if not images:
        images = '未包含有效图片数据'
    return (
        "请扮演时尚内容分析师，对下列小红书笔记进行风格分析，输出内容包括：1）整体风格关键词；"
        " 2）可能的色彩或视觉指向；3）建议的调性与适配场景；用简洁的中文描述。附带图片base64以帮助判断：\n"
        f"{meta}\n{images}"
    )


def _extract_response_text(body: Dict) -> str:
    outputs = []
    for block in body.get('output', []):
        for content in block.get('content', []):
            if content.get('type') == 'output_text':
                outputs.append(content.get('text', ''))
    return '\n'.join(outputs).strip()


def _call_llm(prompt: str) -> str:
    _load_llm_config()
    base_url = os.getenv('OPENAI_BASE_URL')
    api_key = os.getenv('OPENAI_API_KEY')
    model = os.getenv('MODEL')
    if not all([base_url, api_key, model]):
        logger.warning('llm config incomplete, skip style analysis')
        return ''
    url = f"{base_url.rstrip('/')}/v1/responses"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': model,
        'input': prompt,
        'temperature': 0.3,
        'max_output_tokens': 1024,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        return _extract_response_text(body)
    except requests.exceptions.RequestException as exc:
        logger.error(f'llm request failed: {exc}')
    except json.JSONDecodeError:
        logger.error('llm response not json')
    return ''


def _convert_images_to_base64(image_urls: List[str]) -> List[str]:
    base64_list = []
    for url in image_urls:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            base64_list.append(base64.b64encode(resp.content).decode('utf-8'))
        except requests.exceptions.RequestException as exc:
            logger.warning(f'failed to download image {url}: {exc}')
    return base64_list


def enrich_note_style(note_info: Dict) -> Dict:
    if not note_info:
        return note_info
    image_urls = note_info.get('image_list', [])
    image_base64_list = _convert_images_to_base64(image_urls)
    note_info['image_base64'] = image_base64_list
    prompt = _build_prompt(note_info, image_base64_list)
    style_text = _call_llm(prompt)
    note_info['style_analysis'] = style_text or '未生成分析'
    note_info['style_updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    return note_info
