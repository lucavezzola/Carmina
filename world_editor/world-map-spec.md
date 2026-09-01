# Carmina world map spec (short version)

This project uses a single JSON world file:

```json
{
  "terrain": {
    "size": 180.0,
    "resolution": 65,
    "heights": [[...]]
  },
  "objects": [
    { "type": "tree", "x": 12, "y": 3.2, "z": 9 },
    { "type": "building", "x": -18, "y": 2.0, "z": -12, "width": 7, "height": 5, "depth": 7, "color": 123456 },
    { "type": "column", "x": 20, "y": 8.5, "z": 6, "radius": 1.0, "height": 6, "rotation": {"x": 0, "y": 0, "z": 0}, "color": 123456 },
    { "type": "platform", "x": 0, "y": 10, "z": 30, "width": 8, "height": 0.8, "depth": 8, "color": 123123 },
    { "type": "ramp", "x": -15, "y": 6.5, "z": 22, "width": 8, "height": 1.2, "depth": 14, "rotation": {"x": 0.35, "y": 0, "z": 0}, "color": 876543 }
  ]
}
```

## Rules

- `terrain.heights` is a `resolution x resolution` height grid.
- `terrain.size` is the square world size; here it is `180`.
- `x` and `z` are horizontal positions; `y` is vertical height.
- Use the same coordinate system for terrain and objects.
- Trees are simple visual obstacles.
- Buildings and platforms are box colliders.
- Columns are cylinder colliders.
- Ramps are rotated boxes.
- The client rebuilds the world from this JSON using Three.js.

## Supported object types

- `tree`: { "type": "tree", "x": 12, "y": 3.2, "z": 9 }
- `building`: { "type": "building", "x": 18, "y": 2.0, "z": -8, "width": 9, "height": 6, "depth": 6, "color": 123456 }
- `platform`: { "type": "platform", "x": 0, "y": 10, "z": 0, "width": 8, "height": 0.8, "depth": 8, "color": 123456 }
- `column`: { "type": "column", "x": 20, "y": 8.5, "z": 6, "radius": 1.0, "height": 6, "rotation": {"x": 0, "y": 0, "z": 0}, "color": 123456 }
- `ramp`: { "type": "ramp", "x": 30, "y": 7.8, "z": 5, "width": 10, "height": 1.2, "depth": 16, "rotation": {"x": 0.25, "y": 0, "z": 0}, "color": 987654 }

## Important generation rules

- Compute object `y` from terrain height when possible.
- For elevated structures, set custom `y` manually.
- Keep terrain grid square and consistent with `size` and `resolution`.
- Use JSON-safe values only.
- Keep colors as numeric hex-like integers.
- The map must be valid for both server logic and browser rendering.