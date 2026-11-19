import sys, traceback
from app.engine import ocr
path = sys.argv[1]
try:
    text = ocr.ocr_image(open(path, "rb").read())
    print("OK, text found:\n", text[:500])
    print(ocr.extract_bill_fields(text))
except Exception:
    traceback.print_exc()