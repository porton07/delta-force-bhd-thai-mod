# Delta Force: Black Hawk Down + Team Sabre — Thai Language Mod

ม็อดภาษาไทยสำหรับเกม **Delta Force: Black Hawk Down** และภาคเสริม **Team Sabre** (ทดสอบบนเวอร์ชัน GOG v1.5.0.5)

## ความสามารถหลัก
- แปลภาษาไทย 6,337 ข้อความ ครอบคลุมทั้งเกมหลักและ Team Sabre (เมนู, หน้าสรุปภารกิจ, อาวุธ/อุปกรณ์, HUD, ข้อความในด่าน)
- ฟอนต์ไทยบิตแมป 15 ขนาด (LINE Seed Sans TH Bold) พร้อมระบบจัดวางสระและวรรณยุกต์บนล่าง
- Hook ตัดบรรทัดภาษาไทย (`0x4f7120`, `0x4f7360`, `0x573e50`) ให้แสดงผลเต็มความกว้างกล่องและไม่ทำตัวอักษรหาย
- รองรับการพิมพ์ภาษาไทยในช่องแชทระหว่างเล่น (แปลงรหัส CP874 / TIS-620 เป็น UTF-8)
- แพตช์ `ImmDisableIME` และ `dgVoodoo2 D3D8 wrapper` สำหรับ Windows 10/11

## โครงสร้างโปรเจกต์
- `tools/thai_runtime.cpp` — C++ x86 runtime hook (`d3d8.dll`) สำหรับเรนเดอร์ไทย, ตัดบรรทัด, พิมพ์ไทย CP874 และส่งต่อ D3D8 ไปยัง dgVoodoo
- `tools/build_full_thai_patch.py` — สคริปต์สร้างฟอนต์ `FNT0` (จำกัดไม่เกิน 16 หน้า), `thai_glyph_map.bin` และแพ็กไฟล์ `.pff` (`localres.pff`, `EXP1.pff`, `resource.pff`)
- `tools/validate_full_thai_patch.py` — สคริปต์ตรวจสอบความถูกต้องของไฟล์ที่สร้าง
- `tools/compile_runtime.cmd` — สคริปต์คอมไพล์ `d3d8.dll` ด้วย Visual Studio 2022 x86
- `translation/game_text_th_latest.csv` — ฐานข้อมูลคำแปลภาษาไทย 6,337 รายการ
- `assets/LINESeedSansTH_Bd.ttf` — ฟอนต์ต้นฉบับ (LINE Seed Sans TH Bold)
- `release/` — สคริปต์ติดตั้ง (`Install-ThaiMod.bat`, `Uninstall-ThaiMod.bat`), คู่มือ (`README-TH.txt`) และคำอธิบายสำหรับ Nexus Mods

## วิธี Build จากซอร์สโค้ด (สำหรับนักพัฒนา)
1. วางไฟล์ต้นฉบับของเกม (`localres.pff`, `EXP1.pff`, `resource.pff`) ไว้ใน `backup/`
2. รันสคริปต์สร้างแพตช์และตรวจสอบ:
   ```bat
   python tools\build_full_thai_patch.py
   python tools\validate_full_thai_patch.py
   ```
3. คอมไพล์ `d3d8.dll` (ต้องมี Visual Studio 2022 C++ x86):
   ```bat
   tools\compile_runtime.cmd
   ```
4. นำไฟล์ผลลัพธ์จาก `build-full-thai\` (`d3d8.dll`, `thai_glyph_map.bin`, `localres.pff`, `EXP1.pff`, `resource.pff`) ไปใช้งานคู่กับ `dfbhd.exe` (ที่แพตช์ `ImmDisableIME` แล้ว) และ `wrappers\dgVoodoo\D3D8.dll`

> หมายเหตุ: Repository นี้เก็บเฉพาะซอร์สโค้ด เครื่องมือ และไฟล์แปลภาษาไทย ไม่รวมไฟล์ลิขสิทธิ์ของตัวเกม (`.pff`, `.exe`, `.dll`)
