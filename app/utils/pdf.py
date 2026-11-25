"""Generador mínimo de PDF de una sola página para documentos operativos."""

def escapar(texto) -> str:
    plano = str(texto or "").encode("latin-1", "replace").decode("latin-1")
    return plano.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def generar_pdf(lineas, nombre: str, tamano=10) -> tuple[bytes, str]:
    contenido = f"BT /F1 {tamano} Tf 50 790 Td 14 TL\n"
    for linea in list(lineas)[:55]:
        contenido += f"({escapar(linea)}) Tj T*\n"
    contenido += "ET\n"
    cuerpo = contenido.encode("latin-1", "replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(cuerpo)).encode() + b" >>\nstream\n" + cuerpo + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    desplazamientos = []
    for indice, objeto in enumerate(objetos, start=1):
        desplazamientos.append(len(pdf))
        pdf += f"{indice} 0 obj\n".encode() + objeto + b"\nendobj\n"
    inicio_xref = len(pdf)
    pdf += f"xref\n0 {len(objetos) + 1}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for desplazamiento in desplazamientos:
        pdf += f"{desplazamiento:010d} 00000 n \n".encode()
    pdf += (
        f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n"
    ).encode()
    return bytes(pdf), nombre
