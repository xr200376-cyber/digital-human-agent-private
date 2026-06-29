# Cover Templates

The cover feature uses local template definitions in `app.cover_templates`.

## Templates

Six short-video cover styles are bundled:

- 爆款橙紫
- 科技蓝
- 成交红
- 黑金质感
- 清爽绿
- 笔记白

These are layout presets, not copied third-party image templates. Each preset defines colors, badge text, title placement, and cover composition rules.

## Generation Flow

1. Select a finished video from the current task or remix output.
2. Extract the first frame with ffmpeg.
3. Crop/scale to 1080x1920.
4. Overlay the selected template style and keyword text.
5. Save `cover.png` and `cover_report.json` under `storage/cover_tasks/{cover_id}/`.

## Source Policy

The design direction follows common public short-video thumbnail patterns: clear focal point, short high-contrast text, and strong platform-safe title placement.

No copyrighted PSD, Canva, CapCut, Jianying, or other marketplace template files are copied into the repository.

## Repository Policy

Generated cover images are task outputs and must remain in `storage/`. Do not commit generated covers, customer videos, customer faces, or customer product images.
