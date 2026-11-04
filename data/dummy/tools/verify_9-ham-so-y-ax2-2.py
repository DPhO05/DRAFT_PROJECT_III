"""Re-derive every boxed answer of 9-ham-so-y-ax2-2.tex (032..051) with sympy."""
from sympy import Abs, Eq, Interval, Rational as R, S, discriminant, expand, minimum, oo, simplify, solve, sqrt, symbols

x, y, m, a, b, k, n = symbols("x y m a b k n", real=True)
roots = lambda e: set(solve(e, x))
tri = lambda P1, P2, P3: Abs((P2[0] - P1[0]) * (P3[1] - P1[1]) - (P3[0] - P1[0]) * (P2[1] - P1[1])) / 2

# 032
f = lambda t: -3 * t**2
assert (f(-1), f(2), f(R(1, 3))) == (-3, -12, R(-1, 3))
assert f(-2) == -12 and f(1) != 3

# 033
assert minimum(4 * x**2, x, S.Reals) == 0 and roots(4 * x**2) == {0}
assert minimum(R(3, 4) * x**2, x, S.Reals) == 0 and roots(R(3, 4) * x**2) == {0}  # -3/4 x^2 = -(3/4 x^2) <= 0
g = lambda t: 4 * t**2
assert -3 < -2 < 0 and g(-3) == 36 > g(-2) == 16

# 034
av = solve(Eq(-6, a * 3), a)
assert av == [-2]
assert roots(-2 * x**2 + 8) == {2, -2}
assert roots(x + 2 * x**2) == {0, R(-1, 2)} and -2 * R(1, 4) == R(-1, 2)

# 035
s = lambda v: R(1, 8) * v**2
assert s(12) == 18
assert [v for v in solve(Eq(s(x), 32), x) if v > 0] == [16] and s(16) == 32
assert simplify(s(2 * x) - 4 * s(x)) == 0

# 036
a36 = solve(Eq(-8, a * 16), a)
assert a36 == [-R(1, 2)]
f = lambda t: -R(1, 2) * t**2
assert -5 < -4 < 0 and f(-5) == R(-25, 2) < f(-4) == -8
assert roots(f(x) + 18) == {6, -6}

# 037
xs = roots(-R(1, 4) * x**2 - (x - 3))
assert xs == {2, -6} and all(-R(1, 4) * u**2 == u - 3 for u in xs)
A37, B37 = (2, -1), (-6, -9)
assert simplify(sqrt((A37[0] - B37[0]) ** 2 + (A37[1] - B37[1]) ** 2) - 8 * sqrt(2)) == 0
assert roots(x**2 + 4 * x - 12) == xs and discriminant(x**2 + 4 * x - 12, x) / 4 == 16

# 038
assert roots(x**2 - 2 * x - 3) == {3, -1} and discriminant(x**2 - 2 * x - 3, x) / 4 == 4
assert (3**2, (-1) ** 2) == (9, 1)
assert roots(x**2 - 4 * x + 4) == {2} and discriminant(x**2 - 4 * x + 4, x) == 0 and 2**2 == 4
assert discriminant(x**2 - x + 1, x) == -3 and roots(x**2 - x + 1) == set()

# 039
F = lambda t: R(1, 2) * t**2
assert expand(F(a + b) - F(a) - F(b) - a * b) == 0
assert F(7) - F(3) - F(4) == 12 == 3 * 4 and (F(7), F(3), F(4)) == (R(49, 2), R(9, 2), 8)

# 040
disc = discriminant(a * x**2 - 2 * x - 1, x) / 4
assert expand(disc - (1 + a)) == 0
a40 = solve(disc, a)
assert a40 == [-1] and expand(-x**2 - 2 * x - 1 - (-(x + 1) ** 2)) == 0
assert roots(-x**2 - (2 * x + 1)) == {-1} and (-1) ** 2 * -1 == -1 == 2 * (-1) + 1

# 041
a41 = solve(Eq(-4, a * 16), a)[0]
assert a41 == -R(1, 4)
assert a41 * 2**2 == -1
assert roots(a41 * x**2 + R(9, 4)) == {3, -3} and R(9, 4) == R(225, 100) and 0 < 3 < 4

# 042: 2x^2 = 4x + m
D42 = discriminant(2 * x**2 - 4 * x - m, x) / 4
assert expand(D42 - (4 + 2 * m)) == 0
assert solve(D42, m) == [-2] and solve(D42 > 0, m).as_set() == Interval.open(-2, oo)
assert roots(2 * x**2 - 4 * x - 6) == {3, -1} and 2 * 3**2 == 18 == 4 * 3 + 6 and 2 == 4 * -1 + 6 == 2 * (-1) ** 2

# 043
xs = roots(x**2 - 2 * x - 8)
assert xs == {-2, 4} and discriminant(x**2 - 2 * x - 8, x) / 4 == 9
A43, B43 = (-2, 4), (4, 16)
assert 2 * A43[0] + 8 == 4 and 2 * B43[0] + 8 == 16
AH, BK, HK = 4, 16, 6
assert HK == 4 - (-2) and (AH + BK) * HK / 2 == 60
assert tri((-2, 4), (4, 16), (4, 0)) + tri((-2, 4), (4, 0), (-2, 0)) == 60  # split into two triangles

# 044
s44 = solve([Eq(a, 2 + b), Eq(9 * a, b - 6)], [a, b])
assert s44 == {a: -1, b: -3}
assert roots(-x**2 - (2 * x - 3)) == {1, -3}

# 045: 2x^2 = 2x + m
D45 = discriminant(2 * x**2 - 2 * x - m, x) / 4
assert expand(D45 - (1 + 2 * m)) == 0 and solve(D45 > 0, m).as_set() == Interval.open(-R(1, 2), oo)
x1, x2 = symbols("x1 x2")
assert expand((x1 + x2) ** 2 - 2 * x1 * x2) == x1**2 + x2**2
assert 1**2 - 2 * (-m / 2) == 1 + m and solve(Eq(1 + m, 5), m) == [4] and 4 > -R(1, 2)
assert roots(2 * x**2 - 2 * x - 4) == {-1, 2} and roots(x**2 - x - 2) == {-1, 2}
assert {(u, 2 * u**2) for u in (-1, 2)} == {(-1, 2), (2, 8)} and (-1) ** 2 + 2**2 == 5
assert 1 - (-1) + (-2) == 0

# 046
t = symbols("t", positive=True)
OA2 = t**2 + t**4; AB = 2 * t
assert solve(Eq(OA2, AB**2), t) == [sqrt(3)]
tv = sqrt(3)
Aq, Bq = (-tv, tv**2), (tv, tv**2)
assert (Aq, Bq) == ((-sqrt(3), 3), (sqrt(3), 3))
OA2v = simplify(OA2.subs(t, tv))
assert OA2v == 12 == simplify((AB**2).subs(t, tv))
assert simplify(R(1, 2) * 2 * tv * 3 - 3 * sqrt(3)) == 0 and simplify(sqrt(3) / 4 * 12 - 3 * sqrt(3)) == 0

# 047
D47 = discriminant(x**2 - 3 * m * x - 18, x)
assert expand(D47 - (9 * m**2 + 72)) == 0
x2 = symbols("x2")
s47 = solve(Eq(-2 * x2**2, -18), x2)
assert set(s47) == {3, -3}
assert {(-2 * v, -2 * v + v) for v in s47} == {(-6, -3), (6, 3)}  # (x1, x1 + x2)
assert {(x1v + v) / 3 for x1v, v in [(-6, 3), (6, -3)]} == {-1, 1}
for mv in (1, -1):
    r = list(solve(x**2 - 3 * mv * x - 18, x))
    assert len(r) == 2 and sorted(map(abs, r)) == [3, 6]
assert roots(x**2 - 3 * x - 18) == {6, -3} and roots(x**2 + 3 * x - 18) == {-6, 3}
A47, B47 = (-3, 3), (6, 12)
assert all(R(1, 3) * p**2 == p + 6 for p in (-3, 6))
assert R(1, 2) * 6 * 3 + R(1, 2) * 6 * 6 == 27 == tri((0, 0), A47, B47)

# 048
a48 = solve(Eq(18, a * 60**2), a)
assert a48 == [R(1, 200)]
y20 = R(1, 200) * 20**2
assert y20 == 2 and y20 - (-2) == 4
assert roots(R(1, 200) * x**2 - 8) == {40, -40} and 8 - (-2) == 10

# 049
y_ = symbols("y_", nonnegative=True)
AM2 = y_ + (y_ - R(3, 2)) ** 2  # x^2 = y
assert expand(AM2 - ((y_ - 1) ** 2 + R(5, 4))) == 0
assert minimum(AM2, y_, Interval(0, oo)) == R(5, 4) and solve(AM2.diff(y_), y_) == [1]
assert simplify(sqrt(R(5, 4)) - sqrt(5) / 2) == 0
assert 1**2 + (1 - R(3, 2)) ** 2 == R(5, 4)
xx = symbols("xx", real=True)
assert minimum(xx**2 + (xx**2 - R(3, 2)) ** 2, xx, S.Reals) == R(5, 4)

# 050
OA2 = a**2 + a**4; OB2 = b**2 + b**4
AB2 = (a - b) ** 2 + (a**2 - b**2) ** 2
assert expand(OA2 + OB2 - AB2) == expand(2 * a * b * (1 + a * b))
b50 = solve(Eq(2 * b, -1), b)[0]
assert b50 == -R(1, 2)
A50, B50 = (2, 4), (b50, b50**2)
assert B50 == (-R(1, 2), R(1, 4))
OAv, OBv = 20, R(5, 16)
assert (A50[0] ** 2 + A50[1] ** 2, B50[0] ** 2 + B50[1] ** 2) == (OAv, OBv)
assert (A50[0] - B50[0]) ** 2 + (A50[1] - B50[1]) ** 2 == OAv + OBv == R(325, 16)
assert simplify(R(1, 2) * sqrt(20) * sqrt(R(5, 16)) - R(5, 4)) == 0 and tri((0, 0), A50, B50) == R(5, 4)
kk = solve([Eq(a**2, k * a + n), Eq(b**2, k * b + n)], [k, n], dict=True)[0]
assert simplify(kk[k] - (a + b)) == 0 and simplify(kk[n] + a * b) == 0
assert kk[n].subs(b, -1 / a).simplify() == 1

# 051: a x^2 = x + 2, S = |x1 - x2|
D51 = discriminant(a * x**2 - x - 2, x)
assert expand(D51 - (1 + 8 * a)) == 0
S2 = simplify((1 / a) ** 2 - 4 * (-2 / a))
assert simplify(S2 - (1 + 8 * a) / a**2) == 0
s51 = solve(Eq((1 + 8 * a) / a**2, 9), a)
assert set(s51) == {1, -R(1, 9)} and all(v > -R(1, 8) and v != 0 for v in s51)
for av_ in s51:
    r = sorted(solve(av_ * x**2 - x - 2, x))
    P = [(v, av_ * v**2) for v in r]
    assert all(py == px + 2 for px, py in P)
    assert tri((0, 0), P[0], P[1]) == 3
assert roots(x**2 - x - 2) == {-1, 2} and roots(x**2 + 9 * x + 18) == {-3, -6}
assert expand((a - 1) * (9 * a + 1) - (9 * a**2 - 8 * a - 1)) == 0

print("verify_9-ham-so-y-ax2-2: all 20 OK")
