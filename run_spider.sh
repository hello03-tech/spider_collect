#!/usr/bin/env bash
set -euo pipefail

QUERY="设计方案"
COUNT=2
SKIP_STYLE=0
EXTRACT_IMAGES=1
NOTE_IDS=""
SAVE_MODE="json"
OUTPUT_NAME=""
WORKERS=5
DEFAULT_OPENAI_BASE_URL="http://14.103.60.158:3001/v1/"
DEFAULT_MODEL="gpt-5"
OPENAI_API_KEY=sk-pQxVgbW6F4oP75fYz5LGHqe7DAoN8BBPkyznYyWPR4kwKPE2


print_usage() {
  cat <<'EOF'
Usage: ./run_spider.sh [options]

Options:
  -q, --query QUERY         specify the search keyword (default: 视觉UI风格)
  -n, --count COUNT         number of notes to crawl (default: 10)
  --no-style-analysis       skip the LLM-based style enrichment step
  --extract-images          after crawling, run analyze_styles.py to extract text from screenshots (default: on)
  --no-extract-images       skip analyze_styles.py image text extraction
  --note-ids ID1,ID2        pass these comma-separated note IDs to analyze_styles (requires --extract-images)
  --save-mode MODE          choose output mode for main.py (json, excel, all, media, etc.; default: json)
  --output-name NAME        override output file name prefix (default: auto timestamp)
  --workers N               number of concurrent note fetchers (default: 4)
  -h, --help                show this message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -q|--query)
      QUERY="$2"
      shift 2
      ;;
    -n|--count)
      COUNT="$2"
      shift 2
      ;;
    --no-style-analysis)
      SKIP_STYLE=1
      shift
      ;;
    --extract-images)
      EXTRACT_IMAGES=1
      shift
      ;;
    --no-extract-images)
      EXTRACT_IMAGES=0
      shift
      ;;
    --note-ids)
      NOTE_IDS="$2"
      shift 2
      ;;
    --save-mode)
      SAVE_MODE="$2"
      shift 2
      ;;
    --output-name)
      OUTPUT_NAME="$2"
      shift 2
      ;;
    --workers)
      WORKERS="$2"
      shift 2
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      print_usage
      exit 1
      ;;
  esac
done

if [[ "$SKIP_STYLE" -eq 1 ]]; then
  export SKIP_STYLE_ANALYSIS=1
fi

echo "Launching Spider_XHS with query='$QUERY', count=$COUNT, skip-style=$SKIP_STYLE"

OPENAI_BASE_URL="${OPENAI_BASE_URL:-$DEFAULT_OPENAI_BASE_URL}"
OPENAI_API_KEY="${OPENAI_API_KEY:?set OPENAI_API_KEY before running}"
MODEL="${MODEL:-$DEFAULT_MODEL}"

if [[ -z "$OUTPUT_NAME" ]]; then
  timestamp=$(date +%Y%m%d%H%M%S)
  safe_query="${QUERY// /_}"
  safe_query="${safe_query//\//_}"
  OUTPUT_NAME="${safe_query}_${timestamp}"
fi

OPENAI_BASE_URL="$OPENAI_BASE_URL" \
OPENAI_API_KEY="$OPENAI_API_KEY" \
MODEL="$MODEL" \
python main.py --query "$QUERY" --count "$COUNT" --save "$SAVE_MODE" --workers "$WORKERS" --output-name "$OUTPUT_NAME"

JSON_DIR="datas/json_datas"
OUTPUT_FILE="$JSON_DIR/$OUTPUT_NAME.json"
NO_IMG_FILE="$JSON_DIR/${OUTPUT_NAME}_no_images.json"
if [[ -f "$OUTPUT_FILE" ]]; then
  python - <<PY
import json, os
source = os.path.abspath(os.path.join("$OUTPUT_FILE"))
target = os.path.abspath(os.path.join("$NO_IMG_FILE"))
with open(source, "r", encoding="utf-8") as f:
    data = json.load(f)
sanitized = []
for note in data:
    note_copy = {k: v for k,v in note.items() if k != "image_base64"}
    sanitized.append(note_copy)
with open(target, "w", encoding="utf-8") as f:
    json.dump(sanitized, f, ensure_ascii=False, indent=2)
print(f"Saved image-free JSON to {target}")
PY
else
  echo "Warning: expected JSON output $OUTPUT_FILE not found; skipping sanitized copy."
fi

if [[ "$EXTRACT_IMAGES" -eq 1 ]]; then
  echo "Running analyze_styles.py to extract image text..."
  if [[ ! -f "$OUTPUT_FILE" ]]; then
    echo "Warning: expected JSON output $OUTPUT_FILE not found; skipping image text extraction."
    exit 0
  fi
  BASE64_INPUT_FILE="$OUTPUT_FILE"

  # analyze_styles.py consumes note["image_base64"]. If style analysis is skipped (or image_base64 is absent),
  # build a lightweight temp file that contains image_base64 by downloading image_list URLs.
  if python - <<PY
import json
from pathlib import Path

p = Path("$OUTPUT_FILE")
if not p.exists():
    raise SystemExit(2)
with p.open(encoding="utf-8") as f:
    notes = json.load(f)
has_any = any(isinstance(n, dict) and n.get("image_base64") for n in notes)
raise SystemExit(0 if has_any else 1)
PY
  then
    :
  else
    BASE64_INPUT_FILE="$JSON_DIR/${OUTPUT_NAME}_with_base64.json"
    echo "Preparing $BASE64_INPUT_FILE (adding image_base64 via downloads) ..."
    python - <<PY
import base64
import json
import socket
import urllib.request
from pathlib import Path

socket.setdefaulttimeout(20)

src = Path("$OUTPUT_FILE")
dst = Path("$BASE64_INPUT_FILE")

with src.open(encoding="utf-8") as f:
    notes = json.load(f)

def fetch_b64(url):
    if not url:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
    return base64.b64encode(raw).decode("utf-8")

out = []
for note in notes:
    if not isinstance(note, dict):
        out.append(note)
        continue
    if note.get("image_base64"):
        out.append(note)
        continue
    urls = note.get("image_list") or []
    b64_list = []
    for u in urls:
        try:
            b64 = fetch_b64(u)
        except Exception:
            b64 = None
        if b64:
            b64_list.append(b64)
    note2 = dict(note)
    note2["image_base64"] = b64_list
    out.append(note2)

dst.parent.mkdir(parents=True, exist_ok=True)
tmp = dst.with_suffix(".tmp")
with tmp.open("w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
tmp.replace(dst)
print(f"Wrote {dst}")
PY
  fi

  note_args=()
  if [[ -n "$NOTE_IDS" ]]; then
    IFS=',' read -r -a parsed_ids <<< "$NOTE_IDS"
    note_args+=(--note-ids "${parsed_ids[@]}")
  fi
  EXTRACT_OUTPUT_NAME="${OUTPUT_NAME}_extract_texts"
  EXTRACT_OUTPUT_FILE="$JSON_DIR/${EXTRACT_OUTPUT_NAME}.json"
  note_args+=(--output-dir "$JSON_DIR" --output-name "$EXTRACT_OUTPUT_NAME" --input-file "$BASE64_INPUT_FILE")
  OPENAI_BASE_URL="$OPENAI_BASE_URL" \
  OPENAI_API_KEY="$OPENAI_API_KEY" \
  MODEL="$MODEL" \
  WORKERS="$WORKERS" \
  python analyze_styles.py "${note_args[@]}"

  # Write extracted image texts back into the original notes JSON under note["images"].
  python - <<PY
import json
from pathlib import Path

notes_path = Path("$OUTPUT_FILE")
extract_path = Path("$EXTRACT_OUTPUT_FILE")

with notes_path.open(encoding="utf-8") as f:
    notes = json.load(f)
with extract_path.open(encoding="utf-8") as f:
    extracted = json.load(f)

by_id = {}
for r in extracted:
    if isinstance(r, dict) and r.get("note_id"):
        by_id[r["note_id"]] = r.get("images") or []

for n in notes:
    if not isinstance(n, dict):
        continue
    note_id = n.get("note_id")
    if not note_id:
        continue
    img_urls = n.get("image_list") or []
    img_texts = by_id.get(note_id)
    if img_texts is None:
        continue
    images = []
    if img_urls:
        for i, url in enumerate(img_urls, 1):
            images.append({"index": i, "url": url, "text": ""})
        for item in img_texts:
            try:
                idx = int(item.get("index"))
            except Exception:
                continue
            if 1 <= idx <= len(images):
                images[idx - 1]["text"] = item.get("text", "") or ""
            else:
                images.append({"index": idx, "url": "", "text": item.get("text", "") or ""})
    else:
        for item in img_texts:
            images.append({"index": item.get("index"), "url": "", "text": item.get("text", "") or ""})
    n["images"] = images

tmp = notes_path.with_suffix(".tmp")
with tmp.open("w", encoding="utf-8") as f:
    json.dump(notes, f, ensure_ascii=False, indent=2)
tmp.replace(notes_path)
print(f"Wrote image texts into {notes_path} under note['images']")

# Keep the sanitized no-images JSON in sync (if present): remove image_base64 but keep images/texts.
no_img_path = Path("$NO_IMG_FILE")
if no_img_path.exists():
    sanitized = []
    for n in notes:
        if isinstance(n, dict) and "image_base64" in n:
            n = {k: v for k, v in n.items() if k != "image_base64"}
        sanitized.append(n)
    tmp2 = no_img_path.with_suffix(".tmp")
    with tmp2.open("w", encoding="utf-8") as f:
        json.dump(sanitized, f, ensure_ascii=False, indent=2)
    tmp2.replace(no_img_path)
    print(f"Updated {no_img_path} (kept note['images'], removed image_base64)")
PY
fi
