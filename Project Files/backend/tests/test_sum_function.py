def sum(x, y):
    return x + y

def test_sum():
    assert sum(2, 3) == 5
    assert sum(-1, 1) == 0
    assert sum(0, 0) == 0
    assert sum(-5, -5) == -10