# Delta Force: Black Hawk Down + Team Sabre — Thai Language Mod (ม็อดภาษาไทย)

## Short Description (สำหรับช่อง Short description — ไม่เกิน 350 ตัวอักษร)

```text
Full Thai translation mod for Delta Force: Black Hawk Down + Team Sabre (6,337 strings). Includes custom Thai bitmap fonts, full-box UI word wrapping, CP874 Thai chat input support, and modern Windows fixes (ImmDisableIME + dgVoodoo2 D3D8 wrapper). Tested on GOG v1.5.0.5.
```

- **Mod Name:** `Delta Force: Black Hawk Down + Team Sabre - Thai Language Mod (ม็อดภาษาไทย)`
- **Game:** `Delta Force: Black Hawk Down`
- **Category:** `Translations` (หรือ `Miscellaneous` / `User Interface`)

---

## Full Description (สำหรับหน้า Detail บน Nexus Mods)

# Delta Force: Black Hawk Down + Team Sabre — ม็อดภาษาไทย (Thai Language Mod)

ม็อดแปลภาษาไทยสำหรับเกม **Delta Force: Black Hawk Down** และภาคเสริม **Team Sabre** พร้อมระบบแสดงผลภาษาไทยและตัวแก้ปัญหาแครชบน Windows ยุคใหม่

## ฟีเจอร์หลัก (Features)
- **แปลภาษาไทย 6,337 ข้อความ** ครอบคลุมทั้งตัวเกมหลักและ Team Sabre (เมนู, หน้าสรุปภารกิจ, อาวุธ/อุปกรณ์, HUD และข้อความในด่าน)
- **ฟอนต์ไทยบิตแมป 15 ขนาด** (LINE Seed Sans TH Bold) พร้อมระบบวางสระและวรรณยุกต์บนล่างถูกต้อง
- **แก้ระบบตัดบรรทัดภาษาไทย (UI & Briefing Word-Wrap)** แสดงผลเต็มความกว้างกล่องข้อความ ไม่มีตัวอักษรหาย
- **รองรับการพิมพ์ภาษาไทยในช่องแชทระหว่างเล่น** (แปลงรหัส CP874 / TIS-620 เป็น UTF-8 อัตโนมัติ)
- **แก้ปัญหาแครช / จอดำบน Windows 10/11** ด้วยแพตช์ `ImmDisableIME` และ `dgVoodoo2 D3D8 wrapper`

## วิธีติดตั้ง (Installation)

### วิธีที่ 1: ติดตั้งอัตโนมัติ (แนะนำ)
1. แตกไฟล์ `DeltaForce_BHD_ThaiMod.zip` และปิดตัวเกมให้เรียบร้อยก่อน
2. ดับเบิลคลิก **`Install-ThaiMod.bat`** *(หากติดตั้งเกมไว้ใน `Program Files` ให้คลิกขวาแล้วเลือก **Run as administrator**)*
3. กด `Y` เพื่อยืนยันโฟลเดอร์เกม *(หรือลากโฟลเดอร์เกมมาวางหากโปรแกรมหาไม่เจอ)*  
   ตัวติดตั้งจะสำรองไฟล์ต้นฉบับไว้ในโฟลเดอร์ `Backup_Original` ให้อัตโนมัติ
4. เข้าเล่นเกมผ่าน `dfbhd.exe` หรือชอร์ตคัตเดิมได้ทันที

### วิธีที่ 2: ติดตั้งแบบก๊อปปี้วางด้วยตัวเอง (Manual)
1. *(แนะนำ)* สำรองไฟล์ต้นฉบับในโฟลเดอร์เกมไว้ก่อน (`dfbhd.exe`, `d3d8.dll`, `localres.pff`, `EXP1.pff`, `resource.pff`, `dgVoodoo.conf`)
2. ก๊อปปี้ไฟล์และโฟลเดอร์ทั้งหมดข้างใน `ModFiles\` ไปวางทับในโฟลเดอร์ที่ติดตั้งเกม
3. ตรวจสอบให้แน่ใจว่ามีครบทั้ง `d3d8.dll`, `thai_glyph_map.bin` และโฟลเดอร์ `wrappers\dgVoodoo\D3D8.dll`

## วิธีถอนการติดตั้ง (Uninstall)
- ดับเบิลคลิก **`Uninstall-ThaiMod.bat`** หรือนำไฟล์จากโฟลเดอร์ `Backup_Original` กลับไปวางทับที่เดิม

## หมายเหตุ (Notes)
- พัฒนาและทดสอบกับตัวเกมเวอร์ชัน **GOG (v1.5.0.5) + Team Sabre**
- รวม **dgVoodoo2 (D3D8 wrapper)** และฟอนต์ **LINE Seed Sans TH Bold**
