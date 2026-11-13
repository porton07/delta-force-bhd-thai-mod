# ทดสอบหน้าเลือกภารกิจภาษาไทย

ตัวทดสอบนี้ใช้คำแปลจาก `translation/game_text_th_latest.csv` สร้างสำเนา
`localres.pff` ที่ `build-campaign-test` โดยไม่เขียนทับ archive หลัก

สิ่งที่แปลในรุ่นทดสอบนี้:

- ป้ายหน้าเลือกแคมเปญและชื่อภารกิจ
- บทสรุปภารกิจ **Bandit's Crossing** ที่เลือกอยู่ในภาพล่าสุด
- ใช้ LINE Seed Sans TH rasterize ข้อความไทยทั้งพยางค์เป็น atlas glyphs

ยังไม่ครอบคลุมข้อความ HUD, บทสนทนา, เป้าหมายระหว่างเล่น หรือ briefing ของภารกิจอื่น

สั่งสร้างใหม่จากโฟลเดอร์เกม:

```powershell
python -X utf8 ThaiPatch/tools/build_campaign_screen_test.py
```

หลังปิดหน้าต่างเกมทดสอบที่เปิดอยู่ ให้รัน `ThaiPatch/Run-ThaiCampaign-Test.cmd`
เพื่อคัดลอก archive ทดสอบเข้า `RunMenuTest` แล้วเปิดเกมสำเนาแยก ไฟล์ `localres.pff`
หลักในโฟลเดอร์เกมจะไม่ถูกแทนที่

การสร้างผ่านการตรวจอ่าน archive กลับครบทุก member แล้ว แต่ยังต้องยืนยันภาพจากการ
รันเกมจริงก่อนถือว่าตัวอักษรและการตัดบรรทัดวางถูกต้อง
