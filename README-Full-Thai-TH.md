# แพตช์ภาษาไทยทั้งเกม

ตัวสร้างแพตช์ใช้คำแปลจาก `translation/game_text_th_latest.csv` และแก้คลังข้อความทั้งสามไฟล์ ได้แก่ `localres.pff`, `EXP1.pff` และ `resource.pff` ตัวช่วยเรนเดอร์แปลง UTF-8 เป็นกลุ่มอักขระไทยที่จัดสระและวรรณยุกต์แล้วก่อนส่งให้ระบบฟอนต์ bitmap ของเกม

## ทดสอบ

1. ปิด Delta Force ทุกหน้าต่างก่อนเริ่ม เพราะเกมเปิดได้ครั้งละหนึ่ง instance
2. ดับเบิลคลิก `Build-Full-Thai.cmd` ที่โฟลเดอร์เกม
3. หน้าต่างเกมทดสอบจะเปิดจาก `ThaiPatch/FullGameTest` โดยไม่เขียนทับไฟล์ติดตั้งหลัก
4. หากตัวช่วยเรนเดอร์เริ่มทำงาน จะมี `thai_runtime.log` ในโฟลเดอร์ทดสอบ

หากสร้างแพตช์ไว้แล้ว ให้ใช้ `Play-Full-Thai.cmd` เพื่อเตรียมสำเนาทดสอบและเปิดเกม

## ไฟล์ที่สร้าง

- `build-full-thai/localres.pff`
- `build-full-thai/EXP1.pff`
- `build-full-thai/resource.pff`
- `build-full-thai/d3d8.dll` และ `thai_glyph_map.bin`

อย่านำคลัง PFF ที่สร้างแล้วไปรันด้วย `dfbhd.exe` โดยไม่มี DLL และ glyph map เพราะเกมเดิมอ่านข้อความแบบ byte ต่อ byte

ไฟล์ต้นฉบับสำรองอยู่ใน `ThaiPatch/backup` สำหรับ localres/EXP1 ส่วน `resource.pff` ต้นฉบับในโฟลเดอร์เกมไม่ถูกแก้ไข
