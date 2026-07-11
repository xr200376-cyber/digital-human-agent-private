from __future__ import annotations

import json
import math
import subprocess
import asyncio
from datetime import datetime
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from playwright.sync_api import sync_playwright


ROOT = Path("G:/app")
RELEASE_ROOT = Path("G:/release")
WORK_ROOT = RELEASE_ROOT / f"digital_human_agent_product_demo_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
SCREEN_DIR = WORK_ROOT / "screens"
AUDIO_DIR = WORK_ROOT / "audio"
SLIDE_DIR = WORK_ROOT / "slides"
SEGMENT_DIR = WORK_ROOT / "segments"
FINAL_VIDEO = WORK_ROOT / "数字人智能体_产品演示_自然女声版.mp4"
NARRATION_TXT = WORK_ROOT / "演示旁白.txt"

WIDTH = 1920
HEIGHT = 1080
FPS = 30


DEMO_VALUES = {
    "reference": "https://v.douyin.com/真实案例链接",
    "script": (
        "今天给大家演示数字人智能体。它可以把参考视频、文案、声音、数字人、"
        "画中画素材和发布流程放到一个工作台里，按步骤生成能直接发布的口播短视频。"
    ),
    "title": "数字人口播短视频制作演示",
    "tags": "数字人\nAI口播\n短视频制作\n本地获客\n内容生产",
    "keywords": "数字人\nAI口播\n获客短视频\n本地生活\n内容生产",
}


SEGMENTS = [
    {
        "image": "full_workbench.png",
        "title": "一页完成数字人口播生产",
        "subtitle": "真实工作台演示",
        "voice": "这是数字人智能体，一套面向本地商家和内容团队的数字人口播短视频生产工具。核心流程都集中在一个工作台里。",
        "bullets": ["IP 学习", "声音和数字人", "剪辑导出", "发布投流"],
    },
    {
        "image": "ip_script.png",
        "title": "第一步：学习参考内容",
        "subtitle": "链接、资料、脚本同屏处理",
        "voice": "第一步，粘贴参考视频或输入产品资料，系统会提取主题、卖点和口播方向。文案可以直接改写，不需要来回切页面。",
        "bullets": ["粘贴参考链接", "识别原始内容", "同步到脚本区"],
    },
    {
        "image": "voice_human.png",
        "title": "第二步：选择声音和数字人",
        "subtitle": "飞影形象 + 阿里云声音克隆",
        "voice": "第二步，选择数字人形象和声音。支持源视频创建形象、克隆声音，也可以使用已配置好的飞影和阿里云能力生成口播。",
        "bullets": ["选择音色", "选择形象", "生成口播视频"],
    },
    {
        "image": "edit_pip.png",
        "title": "第三步：画中画和字幕剪辑",
        "subtitle": "前 8 秒和后 3 秒保留数字人",
        "voice": "第三步，做视频编辑。默认保留前八秒和最后三秒数字人，中间自动插入产品图或素材视频，并同步字幕节奏。",
        "bullets": ["画中画素材", "字幕设置", "自动合成预览"],
    },
    {
        "image": "tags_cover.png",
        "title": "第四步：标题标签和封面",
        "subtitle": "从脚本提取关键词",
        "voice": "第四步，标题、标签、关键词和封面在同一页完成。关键词会从脚本里提取，封面可以用首帧自动生成。",
        "bullets": ["标题", "标签", "关键词", "封面"],
    },
    {
        "image": "music_publish.png",
        "title": "第五步：配乐并导出 MP4",
        "subtitle": "成片、字幕、配乐合成一条视频",
        "voice": "第五步，选择配乐并导出最终 MP4。系统会把数字人口播、画中画、字幕和背景音乐合成到一条成片里。",
        "bullets": ["选择背景音乐", "一键导出", "下载 MP4"],
    },
    {
        "image": "publish_card.png",
        "title": "第六步：发布和投流",
        "subtitle": "辅助发布 + 巨量本地推入口",
        "voice": "最后，进入发布。抖音、小红书、视频号可以走浏览器辅助发布，下面也提供巨量本地推入口，方便客户继续投流获客。",
        "bullets": ["抖音", "小红书", "视频号", "巨量本地推"],
    },
    {
        "image": "full_workbench.png",
        "title": "从脚本到成片再到投流",
        "subtitle": "更适合交付客户体验的短视频生产流程",
        "voice": "从脚本到成片，再到发布和投流，整套流程尽量做到简单、可控、可交付。适合给客户快速体验，也适合团队批量生产。",
        "bullets": ["简单", "可控", "可交付", "可批量"],
    },
]


def ensure_dirs() -> None:
    for path in [WORK_ROOT, SCREEN_DIR, AUDIO_DIR, SLIDE_DIR, SEGMENT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def capture_screenshots() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
        page.goto("http://127.0.0.1:8080/", wait_until="networkidle", timeout=30000)
        page.evaluate(
            """
            (v) => {
              const setValue = (sel, value) => {
                const el = document.querySelector(sel);
                if (el) {
                  el.value = value;
                  el.dispatchEvent(new Event('input', {bubbles:true}));
                }
              };
              const setText = (sel, value) => {
                const el = document.querySelector(sel);
                if (el) el.textContent = value;
              };
              setValue('#sourceVideoReferenceLinkInput', v.reference);
              setValue('#sourceVideoScript', v.script);
              setValue('#sourceVideoGeneratedTitle', v.title);
              setValue('#sourceVideoGeneratedTags', v.tags);
              setValue('#sourceVideoGeneratedKeywords', v.keywords);
              setValue('#sourceVideoCoverKeyword', '数字人口播');
              setText('#sourceVideoReferenceLinkStatus', '参考链接已解析，文案已同步到脚本区。');
              setText('[data-agent-status="ip"]', '已完成 IP 深度学习，可继续生成脚本和素材。');
              setText('[data-agent-status="script"]', '脚本文案会直接作为字幕内容，也可一键改写。');
              setText('[data-agent-status="av"]', '已选择数字人形象和克隆声音，可生成口播视频。');
              setText('[data-agent-status="edit"]', '画中画会保留前 8 秒和最后 3 秒数字人，中间按素材顺序平分插入。');
              setText('[data-agent-status="tags"]', '标题、标签和关键词可从当前脚本中自动提取。');
              setText('[data-agent-status="subtitle"]', '配乐后可直接导出最终 MP4。');
              setText('[data-agent-status="cover"]', '封面会使用当前视频首帧和关键词生成。');
              setText('[data-agent-status="publish"]', '发布前可打开抖音、小红书、视频号浏览器辅助发布，也可进入巨量本地推投流。');
              setText('#sourceVideoProgressTitle', '处理完成');
              setText('#sourceVideoProgressPercent', '100%');
              const fill = document.querySelector('#sourceVideoProgressFill');
              if (fill) fill.style.width = '100%';
              setText('#sourceVideoProgressHint', '已生成画中画字幕成片，可继续添加配乐。');
              const dl = document.querySelector('#downloadSourceVideoFinal');
              if (dl) {
                dl.classList.remove('disabled');
                dl.textContent = '下载 MP4';
              }
              document.body.classList.add('demo-capture');
            }
            """,
            DEMO_VALUES,
        )
        page.wait_for_timeout(1000)
        selectors = [
            ("full_workbench", "body"),
            ("ip_script", ".agent-column-left"),
            ("voice_human", ".agent-card-av"),
            ("edit_pip", ".agent-card-edit"),
            ("tags_cover", ".agent-column-content"),
            ("music_publish", ".agent-column-publish"),
            ("publish_card", ".agent-card-publish"),
        ]
        for name, selector in selectors:
            page.locator(selector).first.screenshot(path=str(SCREEN_DIR / f"{name}.png"), timeout=15000)
        browser.close()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/Dengb.ttf" if bold else "C:/Windows/Fonts/Deng.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def text_width(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=fnt)
    return bbox[2] - bbox[0]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
            continue
        test = current + char
        if text_width(draw, test, fnt) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def rounded_paste(base: Image.Image, src: Image.Image, box: tuple[int, int, int, int], radius: int = 28) -> None:
    x, y, w, h = box
    src = src.convert("RGB")
    src.thumbnail((w, h), Image.Resampling.LANCZOS)
    frame = Image.new("RGBA", (w, h), (10, 15, 27, 255))
    px = (w - src.width) // 2
    py = (h - src.height) // 2
    frame.paste(src.convert("RGBA"), (px, py))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
    shadow = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    shadow_mask = Image.new("L", (w + 40, h + 40), 0)
    ImageDraw.Draw(shadow_mask).rounded_rectangle((20, 20, w + 20, h + 20), radius=radius, fill=160)
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(18))
    shadow.putalpha(shadow_mask)
    base.alpha_composite(shadow, (x - 20, y - 12))
    base.paste(frame, (x, y), mask)
    border = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle((1, 1, w - 2, h - 2), radius=radius, outline=(62, 117, 195, 180), width=2)
    base.alpha_composite(border, (x, y))


def draw_slide(index: int, segment: dict[str, object]) -> Path:
    bg = Image.new("RGBA", (WIDTH, HEIGHT), (5, 7, 13, 255))
    draw = ImageDraw.Draw(bg)
    for i in range(HEIGHT):
        ratio = i / HEIGHT
        color = (
            int(7 + 20 * ratio),
            int(13 + 4 * ratio),
            int(24 + 45 * ratio),
            255,
        )
        draw.line((0, i, WIDTH, i), fill=color)

    accent = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    acc_draw = ImageDraw.Draw(accent)
    acc_draw.ellipse((1300, -220, 2150, 520), fill=(216, 60, 255, 34))
    acc_draw.ellipse((-240, 690, 620, 1260), fill=(38, 136, 255, 28))
    accent = accent.filter(ImageFilter.GaussianBlur(70))
    bg.alpha_composite(accent)

    title_font = font(54, True)
    subtitle_font = font(28, False)
    brand_font = font(26, True)
    bullet_font = font(25, True)
    body_font = font(28, False)
    small_font = font(22, False)

    draw.rounded_rectangle((70, 56, 330, 104), radius=24, fill=(20, 44, 82, 255), outline=(52, 129, 255, 170), width=2)
    draw.text((96, 66), "数字人智能体", font=brand_font, fill=(245, 249, 255))
    draw.text((70, 156), str(segment["title"]), font=title_font, fill=(255, 255, 255))
    draw.text((74, 226), str(segment["subtitle"]), font=subtitle_font, fill=(139, 182, 255))

    y = 318
    for bullet in segment["bullets"]:
        draw.rounded_rectangle((78, y, 98, y + 20), radius=10, fill=(216, 60, 255, 255))
        draw.text((120, y - 6), str(bullet), font=bullet_font, fill=(233, 241, 255))
        y += 56

    voice_lines = wrap_text(draw, str(segment["voice"]), body_font, 560)
    panel_y = 640
    draw.rounded_rectangle((68, panel_y, 690, 940), radius=24, fill=(14, 22, 37, 210), outline=(43, 91, 160, 190), width=2)
    draw.text((102, panel_y + 34), "演示旁白", font=small_font, fill=(124, 211, 252))
    line_y = panel_y + 78
    for line in voice_lines[:5]:
        draw.text((102, line_y), line, font=body_font, fill=(237, 245, 255))
        line_y += 43

    img = Image.open(SCREEN_DIR / str(segment["image"]))
    if segment["image"] == "full_workbench.png":
        box = (742, 154, 1088, 744)
    else:
        box = (790, 126, 1010, 816)
    rounded_paste(bg, img, box, radius=30)

    progress_w = 420
    step_text = f"{index + 1:02d} / {len(SEGMENTS):02d}"
    draw.text((WIDTH - 178, HEIGHT - 72), step_text, font=small_font, fill=(158, 177, 214))
    draw.rounded_rectangle((WIDTH - 612, HEIGHT - 54, WIDTH - 190, HEIGHT - 42), radius=6, fill=(31, 43, 66, 255))
    fill_w = math.floor(progress_w * (index + 1) / len(SEGMENTS))
    draw.rounded_rectangle((WIDTH - 612, HEIGHT - 54, WIDTH - 612 + fill_w, HEIGHT - 42), radius=6, fill=(216, 60, 255, 255))

    out = SLIDE_DIR / f"slide_{index:02d}.png"
    bg.convert("RGB").save(out, quality=95)
    return out


def synthesize_voice(text: str, audio_path: Path) -> None:
    async def _save() -> None:
        communicate = edge_tts.Communicate(
            text=text,
            voice="zh-CN-XiaoxiaoNeural",
            rate="+7%",
            pitch="+2Hz",
            volume="+0%",
        )
        await communicate.save(str(audio_path))

    asyncio.run(_save())


def run_ffmpeg(args: list[str]) -> None:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([exe, "-hide_banner", "-loglevel", "error", *args], check=True)


def build_video() -> None:
    concat_lines: list[str] = []
    narration_lines: list[str] = []
    for index, segment in enumerate(SEGMENTS):
        slide = draw_slide(index, segment)
        audio = AUDIO_DIR / f"voice_{index:02d}.mp3"
        synthesize_voice(str(segment["voice"]), audio)
        video = SEGMENT_DIR / f"segment_{index:02d}.mp4"
        run_ffmpeg(
            [
                "-y",
                "-loop",
                "1",
                "-i",
                str(slide),
                "-i",
                str(audio),
                "-vf",
                f"fps={FPS},format=yuv420p",
                "-af",
                "apad=pad_dur=0.25",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-tune",
                "stillimage",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-shortest",
                str(video),
            ]
        )
        concat_lines.append(f"file '{video.as_posix()}'")
        narration_lines.append(f"{index + 1}. {segment['voice']}")

    concat_file = WORK_ROOT / "concat.txt"
    concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
    NARRATION_TXT.write_text("\n\n".join(narration_lines), encoding="utf-8")
    run_ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(FINAL_VIDEO)])


def probe_video() -> dict[str, object]:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffprobe = str(Path(exe).with_name("ffprobe.exe"))
    if not Path(ffprobe).exists():
        result = subprocess.run(
            [exe, "-hide_banner", "-i", str(FINAL_VIDEO), "-f", "null", "-"],
            capture_output=True,
        )
        stderr = result.stderr.decode("utf-8", errors="replace")
        return {
            "file": str(FINAL_VIDEO),
            "size": FINAL_VIDEO.stat().st_size if FINAL_VIDEO.exists() else 0,
            "ffmpeg_check": result.returncode,
            "info": "\n".join(stderr.splitlines()[:18]),
        }
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(FINAL_VIDEO),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main() -> None:
    ensure_dirs()
    capture_screenshots()
    build_video()
    probe = probe_video()
    print(FINAL_VIDEO)
    print(NARRATION_TXT)
    print(json.dumps(probe, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
