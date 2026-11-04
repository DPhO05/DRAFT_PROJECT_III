"""Re-derive every boxed answer of 8-phan-tich-nhan-tu-2.tex; factors must expand back and be irreducible over Q."""
from sympy import Poly, QQ, Rational, expand, isprime, solve, symbols

x, y, a, b, c, d, n, t = symbols("x y a b c d n t")


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


# 032
check(15 * x**3 * y**2 - 20 * x**2 * y**3 + 5 * x**2 * y**2, [5, x, x, y, y, 3 * x - 4 * y + 1], (x, y))
check((a + 2) ** 2 - 3 * (a + 2), [a + 2, a - 1], (a,))
# 033
check(9 * x**2 + 6 * x + 1, [3 * x + 1, 3 * x + 1], (x,))
check(49 - 16 * y**2, [7 - 4 * y, 7 + 4 * y], (y,))
# 034
check(x * y - 3 * x + 2 * y - 6, [y - 3, x + 2], (x, y))
check(a**2 - a * b - 5 * a + 5 * b, [a - b, a - 5], (a, b))
# 035
assert sorted(solve((2 * x - 3) ** 2 - 25, x)) == [-1, 4]
check((2 * x - 3) ** 2 - 25, [4, x - 4, x + 1], (x,))
assert sorted(solve(x**2 * (x - 2) - 9 * x + 18, x)) == [-3, 2, 3]
check(x**2 * (x - 2) - 9 * x + 18, [x - 2, x - 3, x + 3], (x,))
# 036
assert 63**2 + 2 * 63 * 37 + 37**2 == 10000 == (63 + 37) ** 2
assert 1002**2 - 998**2 == 8000 == 4 * 2000
# 037
check((n + 3) ** 2 - (n - 1) ** 2, [8, n + 1], (n,))
assert all(((k + 3) ** 2 - (k - 1) ** 2) % 8 == 0 for k in range(-200, 201))
# 038
check(x**2 - 7 * x + 12, [x - 3, x - 4], (x,))
check(2 * x**2 + 7 * x + 3, [2 * x + 1, x + 3], (x,))
assert expand(x * (x - 3) - 4 * (x - 3) - (x**2 - 7 * x + 12)) == 0
assert expand(x * (2 * x + 1) + 3 * (2 * x + 1) - (2 * x**2 + 7 * x + 3)) == 0
# 039
check(2 * x**2 - 2 * y**2 + 12 * y - 18, [2, x - y + 3, x + y - 3], (x, y))
assert expand(x**2 - (y - 3) ** 2 - (x**2 - y**2 + 6 * y - 9)) == 0
# 040
check(2 * x**2 - 5 * x * y + 2 * y**2, [2 * x - y, x - 2 * y], (x, y))
assert (2 * 5 - 2) * (5 - 2 * 2) == 8 == 2 * 25 - 5 * 5 * 2 + 2 * 4
# 041
assert sorted(solve(x**2 - 3 * x - 10, x)) == [-2, 5]
check(x**2 - 3 * x - 10, [x - 5, x + 2], (x,))
assert sorted(solve(3 * x**2 + 5 * x - 2, x)) == [-2, Rational(1, 3)]
check(3 * x**2 + 5 * x - 2, [x + 2, 3 * x - 1], (x,))
# 042
h = 45 - 5 * t**2
check(h, [5, 3 - t, 3 + t], (t,))
assert h.subs(t, 2) == 25 == 5 * 1 * 5
assert [s for s in solve(h, t) if s >= 0] == [3]
# 043
check(x**3 - 3 * x**2 + 6 * x - 8, [x - 2, x**2 - x + 4], (x,))
assert expand((x - 2) * (x**2 + 2 * x + 4) - 3 * x * (x - 2) - (x**3 - 3 * x**2 + 6 * x - 8)) == 0
assert expand((x - Rational(1, 2)) ** 2 + Rational(15, 4) - (x**2 - x + 4)) == 0
# 044
assert sorted(solve((2 * x - 1) ** 2 - (x + 4) ** 2, x)) == [-1, 5]
check((2 * x - 1) ** 2 - (x + 4) ** 2, [3, x - 5, x + 1], (x,))
assert (2 * 5 - 1) ** 2 == 81 == (5 + 4) ** 2 and (2 * -1 - 1) ** 2 == 9 == (-1 + 4) ** 2
assert solve(x**3 + 6 * x**2 + 12 * x + 8, x) == [-2]
check(x**3 + 6 * x**2 + 12 * x + 8, [x + 2, x + 2, x + 2], (x,))
# 045
check((x**2 + x) ** 2 - 8 * (x**2 + x) + 12, [x - 1, x + 2, x - 2, x + 3], (x,))
check(t**2 - 8 * t + 12, [t - 2, t - 6], (t,))
check(x**2 + x - 2, [x + 2, x - 1], (x,))
check(x**2 + x - 6, [x + 3, x - 2], (x,))
# 046
poly46 = a**2 - 2 * a * b + b**2 - 4 * c**2 + 4 * c * d - d**2
check(poly46, [a - b - 2 * c + d, a - b + 2 * c - d], (a, b, c, d))
assert expand((a - b) ** 2 - (2 * c - d) ** 2 - poly46) == 0
assert 9**2 - 4**2 == 65 == (9 - 4) * (9 + 4)
# 047
sols47 = sorted((p, q) for p in range(0, 200) for q in range(0, 200) if p * p - q * q == 21)
assert sols47 == [(5, 2), (11, 10)], sols47
# 048
check(n**3 + 3 * n**2 - n - 3, [n - 1, n + 1, n + 3], (n,))
assert all((k**3 + 3 * k**2 - k - 3) % 48 == 0 for k in range(-301, 302, 2))
kk = symbols("kk")
assert expand((2 * kk + 1 - 1) * (2 * kk + 1 + 1) * (2 * kk + 1 + 3) - 8 * kk * (kk + 1) * (kk + 2)) == 0
# 049
check(x**3 - 3 * x**2 + 4, [x + 1, x - 2, x - 2], (x,))
assert expand(x**2 * (x + 1) - 4 * (x - 1) * (x + 1) - (x**3 - 3 * x**2 + 4)) == 0
assert sorted(solve(x**3 - 3 * x**2 + 4, x)) == [-1, 2]
# 050
check(a**3 + b**3 + c**3 - 3 * a * b * c, [a + b + c, a**2 + b**2 + c**2 - a * b - b * c - c * a], (a, b, c))
assert expand((a + b) ** 3 - 3 * a * b * (a + b) - (a**3 + b**3)) == 0
assert expand((a + b) ** 2 - (a + b) * c + c**2 - 3 * a * b - (a**2 + b**2 + c**2 - a * b - b * c - c * a)) == 0
assert expand(a**3 + b**3 + (-a - b) ** 3 - 3 * a * b * (-a - b)) == 0
# 051
P51 = x**4 + 2 * x**3 + 2 * x**2 + 2 * x + 1
check(P51, [x + 1, x + 1, x**2 + 1], (x,))
assert [k for k in range(-500, 501) if isprime(P51.subs(x, k))] == [-2]
assert P51.subs(x, -2) == 5

print("PTNT-2: all 20 answers verified")
