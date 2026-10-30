"""Latest-frame MJPEG transport; slow clients never accumulate a frame queue."""
import asyncio
import time


async def multipart_frames(read, disconnected):
    previous = None
    while not await disconnected():
        started = time.monotonic()
        frame = await read()
        if frame is None:
            return
        content, stamp = frame
        if stamp != previous:
            previous = stamp
            yield (b'--vision-frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                   + str(len(content)).encode('ascii') + b'\r\nX-Detection-Observed-At: '
                   + stamp.encode('ascii') + b'\r\n\r\n' + content + b'\r\n')
        await asyncio.sleep(max(0, .05-(time.monotonic()-started)))
