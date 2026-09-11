import swirengine

game = swirengine.Game("SwirEngine glTF Scene", mode="3d", asset_root="assets")

for instance in swirengine.load_gltf_scene(game.assets.require("models/scene.glb")):
    game.mesh(instance.mesh, name=instance.node_name or f"node-{instance.node_index}")

game.camera.position.z = 6.0
game.camera.look_at((0.0, 0.0, 0.0))
game.show_debug()
game.run()
