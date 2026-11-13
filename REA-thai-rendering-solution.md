# REA findings: Thai menu rendering

## Findings from the shipped executable

REA analyzed the installed `dfbhd.exe` (SHA-256 `693676b5fb96012d32ee395ac23b4a8bf4d7dd9a9f25ae8e500749a2f0df34ea`) with Ghidra 12.1.4.

- `FUN_005ad4a0` (`ev_868d710dbfaaf30e2ecf6b796fd4aad86bb278902bb4defec9424b6281832cd1`) builds bitmap fonts using `CreateFontA`, `GetTextExtentPoint32A`, and `ExtTextOutA`, passing one byte per glyph. This path has no Thai cluster shaping, so feeding Thai bytes directly can lose characters or place vowels and tone marks incorrectly.
- `FUN_005acff0` (`ev_7cb6c0131b136ba701009ec65603fa848cda2867ef011f7c754aea434db1625c`) loads 224 glyph records and 256x256 bitmap pages from the `FNT0` font resource. This gives us a supported route to replace selected existing glyphs without changing the executable.
- `FUN_005adb60` (`ev_660a40653714830888ded0e2864011a5889d4833edeff7de5f5b3b0240c0857c`) measures strings byte by byte from glyph UVs. It will correctly advance a single carrier byte by the width of a replacement glyph.
- `dfvmenus.mnu` assigns all five main-menu buttons to `Impact50`: Single Player (string 225), Multiplayer (221), Player Info (216), Options (222), and Exit (219). The five replacements therefore belong in `Impact50.fnt`.

## Applied approach

The patch uses printable ASCII carrier bytes (`~`, `^`, `|`, `_`, and `` ` ``). Each carrier maps to one complete Thai menu label, rasterized with the supplied LINE Seed Sans TH Bold font and Windows GDI's Unicode text layout before insertion into an added `Impact50.fnt` atlas page. The text resource stores only the carrier byte, so the old engine does not split a Thai syllable into separately positioned marks. This is why the Sara Ee and Mai Tho in `ตั้งค่าเกมนี้` remain attached in the atlas preview.

REA's loader pseudocode also exposed a bug in the first installed build: each glyph record begins with an integer atlas-page index followed by four floating-point UV values. The first build incorrectly wrote all five fields as floats, making the new page index invalid and causing replacement labels not to draw. `build_menu_test.py` now writes the record as `<I4f`; the five carriers point to page 3 in the new four-page font, and the rebuilt PFF passed the archive round-trip check.

The rebuilt root `localres.pff` passes archive round-trip validation. The currently running isolated `RunMenuTest/localres.pff` is still the prior build because it is a hard link to the archive that was replaced during the fix; the launcher refreshes it after the game closes. The preview is visual evidence for the shaped atlas glyphs, not proof that the game has drawn the buttons. Runtime menu rendering still needs confirmation after restarting the running game.

## Evidence and limits

The executable analysis supports the byte-oriented renderer and `FNT0` loading behavior. The menu configuration and PFF member inventory support the selected font and string indexes. The atlas preview confirms the glyph appearance. Captures made by the automated test harness were black and do not establish the game's rendered menu. No claim is made that this five-label technique enables arbitrary Thai dialogue or player-entered text.
