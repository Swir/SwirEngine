from swirengine import Color, Game, ParticleEmitter2D


game = Game("SwirEngine 1.2 Particle VFX", 1280, 720, mode="2d")

sparks = game.add(
    ParticleEmitter2D(
        640,
        360,
        max_particles=2048,
        rate=220,
        lifetime=(0.25, 0.9),
        speed=(80, 300),
        angle=(15, 165),
        size=(2, 8),
        gravity=(0, -420),
        color=Color(1.0, 0.85, 0.2, 1.0),
        end_color=Color(1.0, 0.1, 0.0, 0.0),
        end_size_scale=0.1,
        drag=1.2,
        rotation=(0, 360),
        angular_velocity=(-540, 540),
        emission_shape="ring",
        emission_size=(34, 34),
        seed=7,
    )
)


@game.update
def update(dt: float) -> None:
    sparks.update(dt)
    if game.key("SPACE"):
        sparks.burst(24)


game.run()
