# Design QA - Card 02 and PIP Modal

- Source reference: `D:\Backup\xwechat_files\wxid_rm27hl739b7222_616c\temp\RWTemp\2026-06\ce817f2da769d6f7d0095f064b3f7555.png`
- Implementation screenshot: `G:\app\design-qa-card2-reference-view-top.png`
- Modal screenshot: `G:\app\design-qa-card2-pip-modal.png`
- URL verified: `http://127.0.0.1:8080/`

Result: Pass.

Checks:
- Card 02 uses the compact reference layout with audio controls, language, avatar selection, primary actions, and video preview in one card.
- PIP material selection opens as a modal from Card 03 instead of expanding inline.
- Modal contains upload, preview grid, confirm, generate, and download actions.
- Served HTML uses `20260616-card2-reference-pip-modal`; old `reference-link-textarea` script reference is absent.
