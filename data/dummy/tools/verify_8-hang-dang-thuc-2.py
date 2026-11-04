"""Re-derive every boxed answer of bank-mo-rong/8-hang-dang-thuc-2.tex."""
from sympy import Eq, Rational, expand, factor, simplify, solve, symbols

x, y, a, b, c, n, t = symbols("x y a b c n t")

# 032
assert expand((x + 4) ** 2) == x**2 + 8 * x + 16
assert expand((3 * y - 2) ** 2) == 9 * y**2 - 12 * y + 4
assert expand((5 * a + 3 * b) ** 2) == 25 * a**2 + 30 * a * b + 9 * b**2
# 033
assert expand((x + 4) ** 3) == x**3 + 12 * x**2 + 48 * x + 64
assert expand((2 * y - 3) ** 3) == 8 * y**3 - 36 * y**2 + 54 * y - 27
assert expand((a + 2 * b) ** 3) == a**3 + 6 * a**2 * b + 12 * a * b**2 + 8 * b**3
# 034
assert 75**2 - 25**2 == (75 - 25) * (75 + 25) == 5000
assert 53**2 + 94 * 53 + 47**2 == (53 + 47) ** 2 == 10_000
assert 101**3 - 3 * 101**2 + 3 * 101 - 1 == (101 - 1) ** 3 == 1_000_000
# 035
assert expand((x + 3) ** 2 - (x - 3) ** 2) == 12 * x
assert expand((2 * a - b) ** 2 + (2 * a + b) ** 2 - 2 * (4 * a**2 - b**2)) == 4 * b**2
assert expand((x + 2) * (x**2 - 2 * x + 4)) == x**3 + 8
assert expand((x + 2) * (x**2 - 2 * x + 4) - (x**3 - 1)) == 9
# 036
assert 105 * 95 == 100**2 - 5**2 == 9975
assert 97**2 == 100**2 - 2 * 100 * 3 + 3**2 == 9409
assert 9975 - 9409 == 566
# 037
assert expand((x + y) * (x**2 - x * y + y**2) + (x - y) * (x**2 + x * y + y**2) - 2 * x**3) == 0
# 038
sols = [s for s in solve([4 * x**2 + 9 * y**2 - 25, x * y - 2], [x, y], dict=True) if s[x].is_real and s[y].is_real and s[x] > 0 and s[y] > 0 and 2 * s[x] > 3 * s[y]]
assert sols == [{x: 2, y: 1}], sols
assert expand((2 * x + 3 * y) ** 2 - ((4 * x**2 + 9 * y**2) + 12 * x * y)) == 0
assert expand((2 * x - 3 * y) ** 2 - ((4 * x**2 + 9 * y**2) - 12 * x * y)) == 0
assert 25 + 12 * 2 == 49 and 25 - 12 * 2 == 1 and 2 * 2 + 3 * 1 == 7 and 2 * 2 - 3 * 1 == 1
# 039: a + b = 14, ab = 45, a > b
assert expand((a + b) ** 2 - (a - b) ** 2 - 4 * a * b) == 0
assert 14**2 - 4 * 45 == 16
r = [s for s in solve([a + b - 14, a * b - 45], [a, b], dict=True) if s[a] > s[b]]
assert r == [{a: 9, b: 5}] and 2 * (9 + 5) == 28 and 9 * 5 == 45 and 9 - 5 == 4
# 040
A = 4 * x**2 + 4 * x + 5
B = 7 + 6 * x - 9 * x**2
assert expand((2 * x + 1) ** 2 + 4 - A) == 0 and A.subs(x, Rational(-1, 2)) == 4
assert expand(-((3 * x - 1) ** 2) + 8 - B) == 0 and B.subs(x, Rational(1, 3)) == 8
assert solve(A.diff(x), x) == [Rational(-1, 2)] and solve(B.diff(x), x) == [Rational(1, 3)]
# 041: u = a - b = 2, a^2 + ab + b^2 = 7
r = solve([a - b - 2, a**2 + a * b + b**2 - 7], [a, b], dict=True)
assert r and all(simplify(s[a] ** 3 - s[b] ** 3 - 14) == 0 and simplify(s[a] * s[b] - 1) == 0 and simplify(s[a] ** 2 + s[b] ** 2 - 6) == 0 for s in r)
assert expand((a - b) ** 2 - ((a**2 + a * b + b**2) - 3 * a * b)) == 0
# 042
assert expand((x - Rational(5, 2)) ** 2 + Rational(3, 4) - (x**2 - 5 * x + 7)) == 0
assert expand(-((x - Rational(3, 2)) ** 2) - Rational(7, 4) - (-(x**2) + 3 * x - 4)) == 0
# 043
assert expand((n + 7) ** 2 - (n - 5) ** 2) == 24 * n + 24
assert expand((5 * n + 3) ** 2 - (5 * n - 3) ** 2) == 60 * n
assert all(((j + 7) ** 2 - (j - 5) ** 2) % 24 == 0 and ((5 * j + 3) ** 2 - (5 * j - 3) ** 2) % 60 == 0 for j in range(-200, 200))
# 044
M = (x + 3) ** 3 - (x - 3) ** 3 - 18 * x**2 - 2 * x
assert expand(M) == 54 - 2 * x and M.subs(x, -27) == 108
# 045
assert expand(n * (n + 1) * (n + 2) * (n + 3) + 1 - (n**2 + 3 * n + 1) ** 2) == 0
assert all(int((j * (j + 1) * (j + 2) * (j + 3) + 1) ** 0.5) ** 2 == j * (j + 1) * (j + 2) * (j + 3) + 1 for j in range(0, 200))
# 046
assert sum(k * k * (1 if k % 2 == 0 else -1) for k in range(1, 101)) == 5050 == 100 * 101 // 2
assert all(k**2 - (k - 1) ** 2 == k + (k - 1) for k in range(2, 101, 2))
# 047
r = solve([x - y - 3, x**3 - y**3 - 63], [x, y], dict=True)
assert sorted((s[x], s[y]) for s in r) == [(-1, -4), (4, 1)], r
assert all(s[x] * s[y] == 4 and s[x] ** 2 + s[y] ** 2 == 17 for s in r)
assert expand(x**3 - y**3 - ((x - y) ** 3 + 3 * x * y * (x - y))) == 0
assert factor(y**2 + 3 * y - 4) == (y - 1) * (y + 4)
# 048
assert expand(a**2 + (1 - a) ** 2 - (2 * (a - Rational(1, 2)) ** 2 + Rational(1, 2))) == 0
assert solve((a**2 + (1 - a) ** 2).diff(a), a) == [Rational(1, 2)] and (a**2 + (1 - a) ** 2).subs(a, Rational(1, 2)) == Rational(1, 2)
assert expand((a**3 + (1 - a) ** 3) - (1 - 3 * a * (1 - a))) == 0
assert expand(a**3 + (1 - a) ** 3 - Rational(1, 4) - 3 * (a - Rational(1, 2)) ** 2) == 0  # = 3(a - 1/2)^2 >= 0
# 049
sol = [(X, Y) for X in range(1, 500) for Y in range(1, 500) if X * X - Y * Y == 45]
assert sol == [(7, 2), (9, 6), (23, 22)], sol
# 050
P = x * (x + 3) * (x + 4) * (x + 7)
assert expand(P - ((x**2 + 7 * x + 6) ** 2 - 36)) == 0
assert factor(x**2 + 7 * x + 6) == (x + 1) * (x + 6)
assert P.subs(x, -1) == -36 and P.subs(x, -6) == -36
assert min(P.subs(x, Rational(k, 4)) for k in range(-80, 80)) == -36
# 051
assert expand(n**4 + 4 - (n**2 - 2 * n + 2) * (n**2 + 2 * n + 2)) == 0
for m in range(2, 300):
    v = m**4 + 4
    f1, f2 = m * m - 2 * m + 2, m * m + 2 * m + 2
    assert f1 * f2 == v and 1 < f1 < f2
assert 2**4 + 4 == 2 * 10 and 3**4 + 4 == 5 * 17
print("HDT-2: all 20 answers verified")
