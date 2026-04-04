class OCRBackendType:
    AUTO = "auto"
    RAPIDOCR = "rapidocr"
    VISION = "vision"


OCR_BACKEND_VALUES = (
    OCRBackendType.AUTO,
    OCRBackendType.RAPIDOCR,
    OCRBackendType.VISION,
)

OCR_BACKEND_VERIFY = "|".join(OCR_BACKEND_VALUES)
