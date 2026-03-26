from pathlib import Path
import textwrap

MD_IN = Path('paper/India_ELG_Research_Paper.md')
PDF_OUT = Path('paper/India_ELG_Research_Paper.pdf')

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
LEFT_MARGIN = 46
TOP_Y = 800
LINE_HEIGHT = 13
MAX_CHARS = 104
LINES_PER_PAGE = 35


def esc(text: str) -> str:
    return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def md_to_lines(md: str):
    lines = []
    for raw in md.splitlines():
        s = raw.rstrip()
        if not s.strip():
            lines.append('')
            continue

        stripped = s.strip()
        if stripped.startswith('#'):
            heading = stripped.lstrip('#').strip().upper()
            lines.append(heading)
            lines.append('')
            continue

        # keep bullets readable
        if stripped.startswith('- ') or stripped[:3].isdigit() and stripped[1:3] == '. ':
            wrapped = textwrap.wrap(stripped, width=MAX_CHARS, subsequent_indent='  ')
        else:
            wrapped = textwrap.wrap(stripped, width=MAX_CHARS)

        if not wrapped:
            lines.append('')
        else:
            lines.extend(wrapped)
    return lines


def page_stream(page_lines, page_no):
    y = TOP_Y
    cmds = ['BT', '/F1 10 Tf', f'{LEFT_MARGIN} {y} Td']
    header = f'India ELG Research Paper Draft - page {page_no}'
    cmds += [f'({esc(header)}) Tj', '0 -16 Td']
    for line in page_lines:
        cmds.append(f'({esc(line)}) Tj')
        cmds.append(f'0 -{LINE_HEIGHT} Td')
    cmds.append('ET')
    return '\n'.join(cmds).encode()


def build_pdf(pages):
    objects = []

    def add_obj(data: bytes):
        objects.append(data)
        return len(objects)

    font_id = add_obj(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')

    content_ids = []
    for page in pages:
        cid = add_obj(f'<< /Length {len(page)} >>\nstream\n'.encode() + page + b'\nendstream')
        content_ids.append(cid)

    pages_placeholder = add_obj(b'PLACEHOLDER')
    page_ids = []
    kids = []
    for cid in content_ids:
        page_obj = (
            f'<< /Type /Page /Parent {pages_placeholder} 0 R '
            f'/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] '
            f'/Resources << /Font << /F1 {font_id} 0 R >> >> '
            f'/Contents {cid} 0 R >>'
        ).encode()
        pid = add_obj(page_obj)
        page_ids.append(pid)
        kids.append(f'{pid} 0 R')

    pages_obj = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(page_ids)} >>".encode()
    objects[pages_placeholder - 1] = pages_obj
    catalog_id = add_obj(f'<< /Type /Catalog /Pages {pages_placeholder} 0 R >>'.encode())

    pdf = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f'{i} 0 obj\n'.encode())
        pdf.extend(obj)
        pdf.extend(b'\nendobj\n')

    xref_pos = len(pdf)
    pdf.extend(f'xref\n0 {len(objects)+1}\n'.encode())
    pdf.extend(b'0000000000 65535 f \n')
    for i in range(1, len(objects) + 1):
        pdf.extend(f'{offsets[i]:010d} 00000 n \n'.encode())

    pdf.extend(f'trailer\n<< /Size {len(objects)+1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n'.encode())
    return pdf


def main():
    if not MD_IN.exists():
        raise FileNotFoundError(f'Missing input file: {MD_IN}')

    lines = md_to_lines(MD_IN.read_text(encoding='utf-8'))
    pages = []
    page_no = 1
    for i in range(0, len(lines), LINES_PER_PAGE):
        pages.append(page_stream(lines[i:i + LINES_PER_PAGE], page_no))
        page_no += 1

    PDF_OUT.write_bytes(build_pdf(pages))
    print(f'Wrote {PDF_OUT} with {len(pages)} pages')


if __name__ == '__main__':
    main()
