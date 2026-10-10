# In plain English: Creates QR image data for membership verification and ticket admission.
"""Local QR images; opaque codes never leave the localhost application."""

import base64
import io
import qrcode


def image_data(text):
    code = qrcode.QRCode(box_size=6, border=4)
    code.add_data(text)
    code.make(fit=True)
    image = code.make_image(fill_color="#153e30", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode(
        "ascii"
    )
