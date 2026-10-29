"""Re-derive every boxed answer of 8-phan-tich-nhan-tu.tex; factors must expand back and be irreducible over Q."""
from sympy import Poly, QQ, Rational, expand, factor_list, solve, symbols

x, y, z, a, b, n = symbols("x y z a b n")


def check(orig, factors, gens):
    """expand(product) == orig and every non-constant factor irreducible over Q."""
    prod = 1
    for f in factors:
        prod *= f
    assert expand(prod - orig) == 0, (orig, factors)
    for f in factors:
        p = Poly(f, *gens, domain=QQ)
        if p.total_degree() > 0:
            assert p.is_irreducible, f


# 001
check(4 * x**2 * y - 6 * x * y**2, [2, x, y, 2 * x - 3 * y], (x, y))
check(5 * x * (x - 2) - 4 * (x - 2), [x - 2, 5 * x - 4], (x,))
# 002
check(x**2 - 10 * x + 25, [x - 5, x - 5], (x,))
check(4 * x**2 - 9 * y**2, [2 * x - 3 * y, 2 * x + 3 * y], (x, y))
check(8 * x**3 - 1, [2 * x - 1, 4 * x**2 + 2 * x + 1], (x,))
# 003
check(x**2 - x * y + 3 * x - 3 * y, [x - y, x + 3], (x, y))
check(2 * x * y + 3 * z + 6 * y + x * z, [x + 3, 2 * y + z], (x, y, z))
# 004
check(a**2 - 4 * b**2, [a - 2 * b, a + 2 * b], (a, b))
assert 46**2 - 4 * 2**2 == 2100 == 42 * 50
# 005
check(x**3 - 4 * x**2 + 4 * x - x * y**2, [x, x - y - 2, x + y - 2], (x, y))
# 006
check(3 * x**2 - 8 * x + 4, [3 * x - 2, x - 2], (x,))
assert expand((2 * x - 2) ** 2 - x**2 - (3 * x**2 - 8 * x + 4)) == 0  # cách 2
# 007
check(2 * x**3 - x**2 - 8 * x + 4, [2 * x - 1, x - 2, x + 2], (x,))
assert sorted(solve(2 * x**3 - x**2 - 8 * x + 4, x)) == [-2, Rational(1, 2), 2]
# 008
check(x**2 - 2 * x * y + y**2 - 3 * x + 3 * y + 2, [x - y - 1, x - y - 2], (x, y))
# 009
check(n**3 - n, [n - 1, n, n + 1], (n,))
assert all((k**3 - k) % 6 == 0 for k in range(-200, 201))
# 010
check((x + 1) * (x + 2) * (x + 3) * (x + 4) - 24, [x, x + 5, x**2 + 5 * x + 10], (x,))
assert expand((x + Rational(5, 2)) ** 2 + Rational(15, 4) - (x**2 + 5 * x + 10)) == 0
assert len(factor_list(expand((x + 1) * (x + 2) * (x + 3) * (x + 4) - 24))[1]) == 3
# 011
check(4 * (x - 3) ** 2 - 8 * (x - 3), [4, x - 3, x - 5], (x,))
check(3 * x * (x - y) + 5 * y * (y - x), [x - y, 3 * x - 5 * y], (x, y))
# 012
check(x**2 - y**2 - 2 * y - 1, [x - y - 1, x + y + 1], (x, y))
assert (93**2 - 6**2 - 2 * 6 - 1) == 8600 == 86 * 100
# 013
assert sorted(solve(x * (x - 3) - 2 * x + 6, x)) == [2, 3]
check(x * (x - 3) - 2 * x + 6, [x - 3, x - 2], (x,))
assert sorted(solve(x**3 - 16 * x, x)) == [-4, 0, 4]
check(x**3 - 16 * x, [x, x - 4, x + 4], (x,))
# 014
check(x**3 + y**3 + 2 * x + 2 * y, [x + y, x**2 - x * y + y**2 + 2], (x, y))
check(x**3 - 3 * x**2 + 3 * x - 1 - 8 * y**3,
      [x - 2 * y - 1, x**2 + 2 * x * y + 4 * y**2 - 2 * x - 2 * y + 1], (x, y))
assert expand((x - 1) ** 2 + 2 * y * (x - 1) + 4 * y**2 - (x**2 + 2 * x * y + 4 * y**2 - 2 * x - 2 * y + 1)) == 0
# 015
check(x**2 - 5 * x * y + 6 * y**2, [x - 2 * y, x - 3 * y], (x, y))
check(x**2 - 5 * x * y + 6 * y**2 - x + 2 * y, [x - 2 * y, x - 3 * y - 1], (x, y))
# 016
check(x**3 + 5 * x**2 + 6 * x, [x, x + 2, x + 3], (x,))
assert [(p, q) for p in range(1, 10) for q in range(1, p) if p + q == 5 and p * q == 6] == [(3, 2)]
assert (4**3 + 5 * 4**2 + 6 * 4) == 168 == 4 * 6 * 7
# 017
check(x**3 - 7 * x + 6, [x - 1, x - 2, x + 3], (x,))
assert expand((x**3 - x) - (6 * x - 6) - (x**3 - 7 * x + 6)) == 0
assert expand((x**3 - 1) - (7 * x - 7) - (x**3 - 7 * x + 6)) == 0
# 018
check(x**4 + 64, [x**2 - 4 * x + 8, x**2 + 4 * x + 8], (x,))
# 019
sols = sorted((X, Y) for X in range(-50, 51) for Y in range(-50, 51) if X * Y + 2 * X - 3 * Y == 11)
assert sols == sorted([(4, 3), (8, -1), (2, -7), (-2, -3)]), sols
assert expand((x - 3) * (y + 2) - (x * y + 2 * x - 3 * y - 6)) == 0
# 020
check(x**5 + x + 1, [x**2 + x + 1, x**3 - x**2 + 1], (x,))
# 021
check(-Rational(1, 2) * x**3 * y + x**2 * y**2 - Rational(3, 2) * x**2 * y, [-Rational(1, 2), x, x, y, x - 2 * y + 3], (x, y))
check(2 * x * (x + 5) + x + 5, [x + 5, 2 * x + 1], (x,))
# 022
assert all((5 ** (j + 2) + 5 ** (j + 1) + 5**j) == 31 * 5**j for j in range(0, 30))
# 023
check((2 * x + 1) ** 2 - (x - 3) ** 2, [x + 4, 3 * x - 2], (x,))
check(x**3 + 9 * x**2 + 27 * x + 27, [x + 3, x + 3, x + 3], (x,))
check((x - 1) ** 3 + 8, [x + 1, x**2 - 4 * x + 7], (x,))
# 024
check((x**2 + 4) ** 2 - 16 * x**2, [x - 2, x - 2, x + 2, x + 2], (x,))
check(x**6 - 64, [x - 2, x + 2, x**2 + 2 * x + 4, x**2 - 2 * x + 4], (x,))
# 025
check(4 * x**2 * y**2 - (x**2 + y**2 - z**2) ** 2,
      [x + y + z, x + y - z, y + z - x, z + x - y], (x, y, z))
tri = [(p, q, s) for p in range(1, 12) for q in range(1, 12) for s in range(1, 12) if p < q + s and q < s + p and s < p + q]
assert all(4 * p**2 * q**2 - (p**2 + q**2 - s**2) ** 2 > 0 for p, q, s in tri)
# 026
check(x**2 * y + x * y**2 + x**2 * z + x * z**2 + y**2 * z + y * z**2 + 2 * x * y * z,
      [x + y, y + z, z + x], (x, y, z))
# 027
check(x**2 + 5 * x - 14, [x + 7, x - 2], (x,))
check(-(x**2) + 4 * x + 5, [x + 1, 5 - x], (x,))
# 028
check(x**4 - 5 * x**2 + 4, [x - 1, x + 1, x - 2, x + 2], (x,))
check(x**4 + x**2 - 20, [x - 2, x + 2, x**2 + 5], (x,))
# 029
w = [s for s in solve(x * (x + 3) - 40, x) if s > 0]
assert w == [5] and 2 * (w[0] + w[0] + 3) == 26
# 030
eq30 = (x - 3) ** 3 + (x + 1) ** 3 - 8 * (x - 1) ** 3
assert sorted(solve(eq30, x)) == [-1, 1, 3]
assert expand(-eq30 - 6 * (x - 3) * (x - 1) * (x + 1)) == 0
assert expand((x - 3) ** 3 + (x + 1) ** 3) == 2 * x**3 - 6 * x**2 + 30 * x - 26
# 031
A31 = 1
for kk in range(2, 11):
    A31 *= Rational(kk**3 - 1, kk**3 + 1)
assert A31 == Rational(37, 55)
B31 = 1
C31 = 1
for kk in range(2, 11):
    B31 *= Rational(kk - 1, kk + 1)
    C31 *= Rational(kk**2 + kk + 1, kk**2 - kk + 1)
assert B31 == Rational(1, 55) and C31 == 37
print("PTNT: all 31 answers verified")
