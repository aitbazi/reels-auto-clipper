import math
import subprocess
from pathlib import Path
from faster_whisper import WhisperModel

# =========================
# Reels 9:16 + Blur Fill + Subtitles + 30s chunks
# =========================

IN_DIR = Path(r"C:\clipper_mvp\input")
OUT_DIR = Path(r"C:\clipper_mvp\output")

CHUNK_SEC = 30
MODEL_NAME = "small"          # "base" faster, "small" good, "medium" better/slower
LANGUAGE = "en"               # set "ar" for Arabic
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

# Quality
CRF = "18"                    # 16-18 high quality, 20 good
PRESET = "slow"               # "slow" better quality, "veryfast" faster

# Last short part
EXPORT_LAST_SHORT = True      # True exports last shorter clip; False stops

# Reels background blur strength
BLUR = 20                     # 12..30 typical

# Subtitle style
FONT_NAME = "Arial"           # change if you want (must be installed)
FONT_SIZE = 68
OUTLINE = 6
SHADOW = 2
MARGIN_V = 140

# Attractive subtitle colors (ASS uses BGR)
COLOR_CYCLE = [
    "&H00FFFF&",  # yellow-ish
    "&HFF00FF&",  # magenta
    "&HFFFF00&",  # cyan
    "&H00FF00&",  # green
    "&H00A5FF&",  # orange-ish
]


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def ensure_tools():
    for tool in ("ffmpeg", "ffprobe"):
        p = run([tool, "-version"])
        if p.returncode != 0:
            raise RuntimeError(f"{tool} not found in PATH.\n{p.stderr}")


def pick_first_video(input_dir: Path) -> Path:
    for ext in ("*.mp4", "*.mkv", "*.mov", "*.webm"):
        vids = sorted(input_dir.glob(ext))
        if vids:
            return vids[0]
    raise FileNotFoundError(f"No video found in: {input_dir}")


def get_duration_sec(video_path: Path) -> float:
    p = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ])
    if p.returncode != 0:
        raise RuntimeError(p.stderr)
    return float(p.stdout.strip())


def ass_time(t: float) -> str:
    cs = int(round(t * 100))
    s = (cs // 100) % 60
    m = (cs // 6000) % 60
    h = (cs // 360000)
    c = cs % 100
    return f"{h:d}:{m:02d}:{s:02d}.{c:02d}"


def escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", " ").strip()


def transcribe_full(video_path: Path):
    print(f"Loading Whisper model: {MODEL_NAME}")
    model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)

    print("Transcribing full video (can take time)...")
    segments, _ = model.transcribe(str(video_path), language=LANGUAGE, vad_filter=True)

    segs = []
    for s in segments:
        txt = (s.text or "").strip()
        if not txt:
            continue
        segs.append((float(s.start), float(s.end), txt))
    return segs


def build_ass_for_chunk(all_segments, chunk_start: float, chunk_end: float, out_ass: Path):
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},{FONT_SIZE},&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H64000000&,-1,0,0,0,100,100,0,0,3,{OUTLINE},{SHADOW},2,70,70,{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    color_idx = 0

    for (s, e, txt) in all_segments:
        if e <= chunk_start or s >= chunk_end:
            continue

        ss = max(s, chunk_start) - chunk_start
        ee = min(e, chunk_end) - chunk_start
        if ee <= 0:
            continue

        txt_clean = escape_ass(txt)
        color = COLOR_CYCLE[color_idx % len(COLOR_CYCLE)]
        color_idx += 1

        styled = r"{\c" + color + r"}" + txt_clean
        lines.append(f"Dialogue: 0,{ass_time(ss)},{ass_time(ee)},Default,,0,0,0,,{styled}\n")

    out_ass.write_text("".join(lines), encoding="utf-8")


def export_chunk_blur_reels(video_path: Path, idx: int, start: float, length: float, ass_path: Path):
    out_mp4 = OUT_DIR / f"clip_{idx:03d}_9x16_blur_subs.mp4"

    # CRITICAL: escape ":" in "C:" for ffmpeg filter syntax
    ass_ff = ass_path.as_posix().replace(":", r"\:")

    # Reels blur-fill background + keep full frame in foreground + burn subtitles
    filter_complex = (
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"boxblur={BLUR}:1,crop=1080:1920[bg];"
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,subtitles='{ass_ff}'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
        "-i", str(video_path),
        "-filter_complex", filter_complex,
        "-r", "30",
        "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(out_mp4)
    ]

    p = run(cmd)
    if p.returncode != 0:
        raise RuntimeError(f"FFmpeg failed for clip {idx}:\n{p.stderr}")

    print("Exported:", out_mp4.name)


def main():
    ensure_tools()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    video = pick_first_video(IN_DIR)
    print("Input video:", video.name)

    duration = get_duration_sec(video)
    print(f"Duration: {duration:.2f} seconds")

    all_segments = transcribe_full(video)
    print(f"Transcript segments: {len(all_segments)}")

    total_chunks = math.ceil(duration / CHUNK_SEC)

    for i in range(total_chunks):
        start = i * CHUNK_SEC
        remaining = duration - start
        if remaining <= 0.2:
            break

        length = min(CHUNK_SEC, remaining)

        if (not EXPORT_LAST_SHORT) and length < CHUNK_SEC:
            print("Last part is shorter than 30s. Stopping.")
            break

        ass_path = OUT_DIR / f"__tmp_{i+1:03d}.ass"
        build_ass_for_chunk(all_segments, start, start + length, ass_path)

        print(f"Creating clip {i+1}/{total_chunks}: {start:.1f}s -> {start+length:.1f}s")
        export_chunk_blur_reels(video, i + 1, start, length, ass_path)

        # Delete temp .ass so you keep only MP4 videos
        try:
            ass_path.unlink(missing_ok=True)
        except Exception:
            pass

    print("Done. Your reels clips are in:", OUT_DIR)


if __name__ == "__main__":
    main()
