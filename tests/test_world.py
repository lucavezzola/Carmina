from src.server.world import generate_world_map, terrain_height_at


def test_generated_columns_store_base_height():
    world = generate_world_map()
    columns = [obj for obj in world["objects"] if obj["type"] == "column"]

    for column in columns:
        assert column["y"] == terrain_height_at(
            world["terrain"]["heights"], column["x"], column["z"]
        )


def test_generated_ramps_store_base_height():
    world = generate_world_map()
    ramps = [obj for obj in world["objects"] if obj["type"] == "ramp"]

    for ramp in ramps:
        terrain_y = terrain_height_at(
            world["terrain"]["heights"], ramp["x"], ramp["z"]
        )
        assert abs(ramp["y"] + ramp["height"] / 2 - (terrain_y + 2.0)) < 1e-9
