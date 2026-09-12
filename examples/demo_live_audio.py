"""Live audio reload example for editor/development workflows.

Run with the optional audio extra installed and place ``theme.ogg`` in ``assets``.
Edit/replace the file while this loop is running: looping music restarts in place.
"""

import time

from swirengine import AssetManager, AudioEngine


assets = AssetManager("assets")
audio = AudioEngine(assets).enable_live_reload()
music = audio.music("theme.ogg", volume=0.65, loop=True)

print("Watching:", music.path)
print("Replace theme.ogg on disk to exercise live reload. Press Ctrl+C to stop.")

try:
    while True:
        for result in audio.poll_live_reload():
            event = audio.reload_events[-1] if audio.reload_events else None
            if event is not None and event.path == result.path:
                print(
                    f"{result.kind}: {result.path} | restarted={event.restarted} "
                    f"stopped={event.stopped} skipped={event.skipped} error={event.error}"
                )
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    audio.shutdown()
