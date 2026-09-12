from swirengine import EditorRuntimeSession, Rectangle2D, Scene

scene = Scene()
player = scene.add(Rectangle2D(10, 20, 32, 32, name="Player"))
session = EditorRuntimeSession(scene, fixed_step=1 / 60)

runtime = session.play()
runtime_player = runtime.find("Player")
runtime_player.x = 999

session.pause()
session.step()
print(session.frame())

session.stop()
print("edit scene x:", player.x)  # still 10: runtime changes are discarded
