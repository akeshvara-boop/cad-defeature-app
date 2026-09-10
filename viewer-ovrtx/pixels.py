import warp as wp

@wp.kernel
def rgba_to_bgra(source: wp.array3d(dtype=wp.uint8), target: wp.array3d(dtype=wp.uint8)):
    y, x = wp.tid()
    target[y, x, 0] = source[y, x, 2]
    target[y, x, 1] = source[y, x, 1]
    target[y, x, 2] = source[y, x, 0]
    target[y, x, 3] = source[y, x, 3]
