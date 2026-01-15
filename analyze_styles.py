import argparse
import base64
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image

BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://14.103.60.158:3001/")
API_KEY = os.environ.get("OPENAI_API_KEY")
MODEL = os.environ.get("MODEL", "gemini-2.5-flash")


def shrink_image_b64(image_b64: str) -> str:
    """Resize the image to keep the payload manageable."""
    raw = base64.b64decode(image_b64)
    with Image.open(io.BytesIO(raw)) as img:
        img = img.convert("RGB")
        img.thumbnail((800, 800))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=60)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def call_llm_for_image(image_b64: str, idx: int) -> str:
    api_url = f"{BASE_URL.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    prompt_text = (
        "Extract every piece of visible text (Chinese or English) from the provided screenshot. "
        "List them in the order they appear and include translations in parentheses if available."
    )
    message_content = [
        {"type": "text", "text": prompt_text},
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{image_b64}",
                "description": f"Image {idx}",
            },
        },
    ]
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a text extraction assistant."},
            {"role": "user", "content": message_content},
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    resp = requests.post(api_url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    body = resp.json()
    choices = body.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "").strip()


def format_comment(comment: dict) -> dict:
    user_info = comment.get("user_info") or {}
    sub_comments = comment.get("sub_comments", [])
    return {
        "id": comment.get("id"),
        "content": comment.get("content"),
        "like_count": comment.get("like_count"),
        "user_id": user_info.get("user_id"),
        "nickname": user_info.get("nickname"),
        "sub_comments": [format_comment(sub) for sub in sub_comments],
    }


def write_results(path: Path, records: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def process_image_task(idx: int, raw_b64: str) -> str:
    shrunk = shrink_image_b64(raw_b64)
    return call_llm_for_image(shrunk, idx)


def parse_args():
    parser = argparse.ArgumentParser(description="Extract text and metadata for Spider_XHS notes.")
    parser.add_argument(
        "--note-ids",
        "-n",
        nargs="+",
        help="Only process these note IDs (default: all notes in datas/json_datas/“视觉UI设计“.json).",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Do not call the LLM for image text extraction; only write textual metadata and comments.",
    )
    parser.add_argument(
        "--output-name",
        "-o",
        default="extracted_texts",
        help="Base name for the output JSON file (default: extracted_texts).",
    )
    parser.add_argument(
        "--output-dir",
        "-d",
        default="datas/json_datas",
        help="Directory where the output JSON is placed (default: datas/json_datas).",
    )
    parser.add_argument(
        "--input-file",
        "-i",
        default="datas/json_datas/“视觉UI设计“.json",
        help="JSON file with note data to summarize (default: datas/json_datas/“视觉UI设计“.json).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if API_KEY is None:
        raise SystemExit("set OPENAI_API_KEY before running")

    json_path = Path(args.input_file)
    if not json_path.exists():
        raise SystemExit(f"{json_path} not found; run spider to generate the data first")
    with json_path.open(encoding="utf-8") as f:
        notes = json.load(f)

    result_path = Path(args.output_dir) / f"{args.output_name}.json"
    existing = []
    if result_path.exists():
        with result_path.open(encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except json.JSONDecodeError:
                existing = []

    worker_count = int(os.environ.get("WORKERS", "3"))
    selected = set(args.note_ids) if args.note_ids else None
    for note in notes:
        note_id = note.get("note_id")
        if selected and note_id not in selected:
            continue
        note_id = note.get("note_id")
        note_texts = {
            "note_url": note.get("note_url", ""),
            "title": note.get("title", ""),
            "description": note.get("desc", ""),
            "tags": note.get("tags", []),
            "interaction_counts": {
                "liked": note.get("liked_count"),
                "collected": note.get("collected_count"),
                "comments": note.get("comment_count"),
                "shares": note.get("share_count"),
            },
            "comments": [format_comment(comment) for comment in note.get("comments", [])],
        }
        extracted = []
        if not args.skip_images:
            images = list(enumerate(note.get("image_base64", []), 1))
            if images:
                print(f"[{note_id}] processing {len(images)} image(s) with {worker_count} worker(s)")
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    future_to_idx = {
                        executor.submit(process_image_task, idx, raw_b64): idx
                        for idx, raw_b64 in images
                    }
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        try:
                            text = future.result()
                            extracted.append({"index": idx, "text": text})
                            print(f"[{note_id}] image {idx} done")
                        except Exception as exc:
                            print(f"[{note_id}] image {idx} failed: {exc}")
        extracted.sort(key=lambda x: x["index"])
        record = {"note_id": note_id, "texts": note_texts, "images": extracted}
        existing.append(record)
        write_results(result_path, existing)
        print(f"[{note_id}] saved {len(extracted)} image texts to {result_path}")

    print("All notes processed.")


if __name__ == "__main__":
    main()
