from tripforge.stops import town_point


def test_boundary_centroid_moves_to_listings_centre():
    assert town_point("boundary", 7.7212, 98.7655, [8.0372, 98.8332]) == (8.0372, 98.8332)


def test_point_hit_is_kept():
    assert town_point("place", 7.8949, 98.2988, [8.0372, 98.8332]) == (7.8949, 98.2988)


def test_far_centre_is_ignored():
    assert town_point("boundary", 3.15, 101.69, [1.35, 103.82]) == (3.15, 101.69)
