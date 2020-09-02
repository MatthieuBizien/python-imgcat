"""
iTerm2 backend for imgcat.
"""
import base64
import io
import os

TMUX_WRAP_ST = b'\033Ptmux;'
TMUX_WRAP_ED = b'\033\\'

OSC = b'\033]'
CSI = b'\033['
ST = b'\a'  # \a = ^G (bell)
MAX_TMUX_BUF_SIZE = 41_000


def _resize_to_len(buf, max_size):
    # Load PIL only if it is mandatory
    import PIL.Image

    # Short path: buffer is small enough
    if len(buf) < max_size:
        return buf

    im = PIL.Image.open(io.BytesIO(buf)).convert("RGB")

    # Is compressing to JPEG enough?
    buf = io.BytesIO()
    im.save(buf, format='jpeg')
    buf = buf.getvalue()
    if len(buf) < max_size:
        return buf

    # Let's decrease progressively the size of the image
    size = 512
    while True:
        if len(buf) < max_size:
            return buf
        im.thumbnail((size, size))
        buf = io.BytesIO()
        im.save(buf, format='jpeg')
        buf = buf.getvalue()
        size = (size * 3) // 4


def _write_image(buf, fp,
                 filename, width, height, preserve_aspect_ratio):
    # need to detect tmux
    is_tmux = 'TMUX' in os.environ and 'tmux' in os.environ['TMUX']

    # tmux: print some margin and the DCS escape sequence for passthrough
    # In tmux mode, we need to first determine the number of actual lines
    if is_tmux:
        buf = _resize_to_len(buf, MAX_TMUX_BUF_SIZE)
        fp.write(b'\n' * height)
        # move the cursers back
        fp.write(CSI + b'?25l')
        fp.write(CSI + str(height).encode() + b"F")  # PEP-461
        fp.write(TMUX_WRAP_ST + b'\033')

    # now starts the iTerm2 file transfer protocol.
    fp.write(OSC)
    fp.write(b'1337;File=inline=1')
    fp.write(b';size=' + str(len(buf)).encode())
    if filename:
        if isinstance(filename, bytes):
            filename_bytes = filename
        else:
            filename_bytes = filename.encode()
        fp.write(b';name=' + base64.b64encode(filename_bytes))
    fp.write(b';height=' + str(height).encode())
    if width:
        fp.write(b';width=' + str(width).encode())
    if not preserve_aspect_ratio:
        fp.write(b';preserveAspectRatio=0')
    fp.write(b':')
    fp.flush()

    buf_base64 = base64.b64encode(buf)
    fp.write(buf_base64)

    fp.write(ST)

    if is_tmux:
        # terminate DCS passthrough mode
        fp.write(TMUX_WRAP_ED)
        # move back the cursor lines down
        fp.write(CSI + str(height).encode() + b"E")
        fp.write(CSI + b'?25h')
    else:
        fp.write(b'\n')

    # flush is needed so that the cursor control sequence can take effect
    fp.flush()
