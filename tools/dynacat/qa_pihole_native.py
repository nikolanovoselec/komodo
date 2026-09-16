import subprocess,sys
import test_networking_lower as t
# Existing harness preserves production head; temporary containers removed in finally.
g=t.page.__wrapped__()
try:
 next(g)
 subprocess.run([sys.executable,'tools/dynacat/qa_pihole_redesign.py','http://127.0.0.1:18146/networking','candidate'],check=True)
finally:g.close()
