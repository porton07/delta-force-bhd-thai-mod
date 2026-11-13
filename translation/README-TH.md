# ข้อความเกมและสคริปต์แปลไทย

`game_text_source.jsonl` และ `game_text_source.csv` มีข้อความจากตาราง RTXT ทุกตารางใน `localres.pff`, `resource.pff` และ `EXP1.pff` รวม 6,717 รายการ โดยเก็บชื่อ archive, ชื่อ member, index, metadata และไบต์ต้นฉบับไว้ครบ ข้อความว่างยังคงอยู่เพื่อไม่ให้ index เคลื่อน

ไฟล์ต้นฉบับของเครื่องมือคือ `ThaiPatch/tools/extract_game_text.py` และ `ThaiPatch/tools/translate_google_free.py` ใช้ Python standard library เท่านั้น ไม่ต้องติดตั้งแพ็กเกจหรือใส่ API key

รันจากโฟลเดอร์เกม:

```powershell
python -X utf8 ThaiPatch/tools/extract_game_text.py
python -X utf8 ThaiPatch/tools/translate_google_free.py --limit 10
```

คำสั่งแรกสร้างไฟล์ต้นฉบับใหม่จาก archive ที่ติดตั้ง คำสั่งที่สองลองแปล 10 รายการเพื่อเช็กผลก่อน ถ้าผลใช้ได้ ให้รันโดยไม่ใส่ `--limit` เพื่อแปลรายการที่เหลือ:

```powershell
python -X utf8 ThaiPatch/tools/translate_google_free.py
```

ผลแปลอยู่ใน `game_text_th.csv` และ `game_text_th.jsonl` สคริปต์สร้าง `google_cache.json` เพื่อ reuse ผลซ้ำและ resume ได้เมื่อหยุดกลางทาง โดยส่งคำขอทีละชิ้น หน่วงอย่างน้อย 0.65 วินาที และแยกข้อความยาวที่ช่องว่าง/ขึ้นบรรทัดใหม่ มันปกป้อง token รูปแบบเกม เช่น `{hot}`, `<cFC8932>`, `%s`, `%i` ระหว่างแปล

ตัวแปลใช้ endpoint `client=gtx` ที่ Google Translate ใช้บนเว็บ ซึ่งไม่ต้องใช้ key แต่เป็น endpoint ที่ไม่มีสัญญา API รองรับ Google อาจเปลี่ยนรูปแบบ จำกัดความถี่ หรือหยุดให้บริการได้ สคริปต์จะ retry, เก็บ cache และหยุดเมื่อคำขอหนึ่งรายการล้มเหลวครบ เพื่อไม่ยิงซ้ำทั้งชุด จากนั้นรันคำสั่งเดิมเพื่อ resume ได้ ควรตรวจคำแปลและตัวแปรเกมก่อนนำกลับเข้า PFF

ขอบเขตนี้ครอบคลุมตารางข้อความ RTXT ใน archive ทั้งสาม ไม่ได้แปล readme/PDF, ชื่อไฟล์, ไฟล์เสียง หรือ source/config ของเมนู และยังไม่ได้เขียนไฟล์แปลกลับเข้าเกม
