from swirengine import Game, Cube3D, Color, Vec3

game = Game("SwirEngine 0.1 - 3D", 1000, 650, mode="3d")
cube = Cube3D(position=Vec3(0, 0, -4), color=Color(0.1, 0.65, 1.0, 1.0))
cube2 = Cube3D(position=Vec3(1.7, 0.3, -6), size=1.3, color=Color(1.0, 0.25, 0.45, 1.0))
game.scene.add(cube)
game.scene.add(cube2)

@game.update
def update(dt):
    cube.rotation.y += 55 * dt
    cube.rotation.x += 25 * dt
    cube2.rotation.y -= 35 * dt
    cube2.rotation.z += 20 * dt

game.run()
