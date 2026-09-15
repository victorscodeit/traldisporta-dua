# -*- coding: utf-8 -*-
import paramiko, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("68.183.154.3", username="root", password="%yn.Qu/Z3WB6Q2Ds:2", timeout=30, allow_agent=False, look_for_keys=False)
script = r'''
import re
scraper = env["aduanas.aeat.taric.scraper"]
raw = scraper.fetch_taric_raw("0702000000")
t = raw.get("text") or ""
i = t.lower().find("svi")
print(t[i:i+800] if i>=0 else t[2000:2800])
print("---")
i2 = t.lower().find("svx")
print(t[i2:i2+500] if i2>=0 else "")
'''
sftp = c.open_sftp()
with sftp.file("/tmp/soivre_tom.py", "w") as f:
    f.write(script)
sftp.close()
_, o, e = c.exec_command(
    "docker cp /tmp/soivre_tom.py odoo-traldisdua:/tmp/soivre_tom.py && "
    "docker exec odoo-traldisdua bash -lc \"odoo shell -d traldisdua16 --http-port=18156 --longpolling-port=18157 < /tmp/soivre_tom.py\"",
    timeout=180,
)
print(o.read().decode("utf-8", "replace")[-4000:])
c.close()
