"""Re-derive every boxed answer of 8-ham-so-bac-nhat-2.tex (032..051) with sympy."""
from sympy import Abs, Eq, Rational as R, S, expand, simplify, solve, sqrt, symbols, minimum, Interval, oo

x, y, m, a, b, t = symbols("x y m a b t")

# 032
g = lambda v: -R(1, 2) * v + 4
assert (g(0), g(6), g(-3)) == (4, 1, R(11, 2))
assert solve(Eq(g(x), 7), x) == [-6] and g(-6) == 7

# 033: y = 2x - 5
d = lambda v: 2 * v - 5
pts = {"A": (0, -5), "B": (3, 2), "C": (-1, -7), "D": (2, 0)}
on = {k for k, (px, py) in pts.items() if d(px) == py}
assert on == {"A", "C"} and d(3) == 1 and d(2) == -1

# 034
assert (3 * 0 - 6, solve(3 * x - 6, x)) == (-6, [2])
assert (-R(2, 3) * 0 + 4, solve(-R(2, 3) * x + 4, x)) == (4, [6])
assert (R(1, 2) * 0, solve(R(1, 2) * x, x), R(1, 2) * 4) == (0, [0], 2)

# 035
b35 = solve(Eq(7, -3 * (-1) + b), b)
assert b35 == [4] and -3 * (-1) + 4 == 7
assert 2 != 0 and -3 != 1  # a) y = -3x + 4 ; b) a = 2, b = -3 != 1

# 036: slope m + 1, m != -1
assert solve(Eq(m + 1, -3), m) == [-4] and -2 != 1 and -4 != -1
assert [v for v in (-3, -2, 0, 5) if (v + 1 > 0)] == [0, 5]  # a) m > -1 means slope > 0
assert [v for v in (-3, -2, 0, 5) if (v + 1 < 0)] == [-3, -2]  # b) m < -1

# 037: l = m/2 + 20
l = lambda v: R(1, 2) * v + 20
assert l(0) == 20 and l(6) == 23 and solve(Eq(l(m), 28), m) == [16]

# 038
M = solve([Eq(y, R(1, 2) * x + 3), Eq(y, -R(3, 2) * x + 7)], [x, y])
assert M == {x: 2, y: 4} and 2 * 2 == 4
assert len({R(1, 2), -R(3, 2), 2}) == 3

# 039
s39 = solve([Eq(4, a + b), Eq(0, -2 * a + b)], [a, b])
assert s39 == {a: R(4, 3), b: R(8, 3)} and R(4, 3) * (-2) + R(8, 3) == 0
assert R(1, 2) * R(8, 3) * 2 == R(8, 3)

# 040
VA = lambda v: 12 * v + 80; VB = lambda v: -8 * v + 260
assert solve(Eq(VA(t), VB(t)), t) == [9] and VA(9) == VB(9) == 188
assert solve(VB(t), t) == [R(65, 2)] and R(65, 2) == 32 + R(1, 2)

# 041: y = (3 - m)x + m - 1
f41 = lambda mv, xv: (3 - mv) * xv + mv - 1
assert solve(f41(m, 0), m) == [1] and 1 != 3
assert solve(Eq(3 - m, 1), m) == [2] and (2 - 1) != 3 and 2 != 3
assert expand(f41(m, 2)) == 5 - m and solve(f41(m, 2), m) == [5] and 5 != 3
assert expand(f41(5, x)) == -2 * x + 4 and solve(f41(5, x), x) == [2]
assert expand(f41(1, x)) == 2 * x

# 042
xi = solve(Eq(2 * x + 3, -x + m), x)[0]
yi = (2 * xi + 3).simplify()
assert simplify(xi - (m - 3) / 3) == 0 and simplify(yi - (2 * m + 3) / 3) == 0
assert solve(Eq(yi, xi), m) == [-6]
assert solve(Eq(2 * x + 3, -x - 6), x) == [-3] and 2 * (-3) + 3 == -3

# 043
A43 = solve([Eq(y, 2 * x - 2), Eq(y, -x + 4)], [x, y])
assert A43 == {x: 2, y: 2}
B43, C43 = (0, -2), (0, 4)
assert R(1, 2) * (C43[1] - B43[1]) * A43[x] == 6

# 044
I = solve([Eq(y, x + 1), Eq(y, 3 * x - 5)], [x, y])
assert I == {x: 3, y: 4}
b44 = solve(Eq(4, -2 * 3 + b), b)
assert b44 == [10] and b44[0] != 1

# 045
A, B, C, D = (solve(-2 * x + 6, x)[0], 0), (0, 6), (solve(-2 * x + 2, x)[0], 0), (0, 2)
assert (A, B, C, D) == ((3, 0), (0, 6), (1, 0), (0, 2)) and 6 != 2
sOAB, sOCD = R(1, 2) * 3 * 6, R(1, 2) * 1 * 2
assert (sOAB, sOCD, sOAB - sOCD) == (9, 1, 8) and 1 < 3 and 2 < 6
shoelace = lambda *P: Abs(sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))) / 2
assert shoelace(A, B, D, C) == 8

# 046
def tien(k):
    return 2 * k if k <= 50 else 100 + 3 * (k - 50)
assert (tien(40), tien(90)) == (80, 220)
assert expand(100 + 3 * (x - 50)) == 3 * x - 50
assert 2 * 50 < 340 and solve(Eq(3 * x - 50, 340), x) == [130] and tien(130) == 340
assert all(tien(k + 20) - tien(k) == 60 for k in range(51, 120))
assert expand((3 * (x + 20) - 50) - (3 * x - 50)) == 60

# 047
f47 = 3 * x + 4
assert expand(f47.subs(x, 2 * x - 1) - (6 * x + 1)) == 0
tt = symbols("tt")
ft = solve(Eq(symbols("F"), 6 * ((tt + 1) / 2) + 1), symbols("F"))[0]
assert expand(ft - (3 * tt + 4)) == 0
f = lambda v: 3 * v + 4
assert (f(1), f(f(1))) == (7, 25)

# 048
A48, B48 = (solve(x + 1, x)[0], 0), (solve(-x + 7, x)[0], 0)
C48 = solve([Eq(y, x + 1), Eq(y, -x + 7)], [x, y])
assert (A48, B48, C48) == ((-1, 0), (7, 0), {x: 3, y: 4})
AB = 7 - (-1)
AC2 = (3 + 1) ** 2 + 4**2; BC2 = (7 - 3) ** 2 + 4**2
assert (AB, AC2, BC2) == (8, 32, 32) and AC2 + BC2 == AB**2
assert simplify(sqrt(AC2) - 4 * sqrt(2)) == 0 and 8 + 2 * 4 * sqrt(2) == 8 + 8 * sqrt(2)

# 049: d3 y = (m+1)x + m, m != -1
I49 = solve([Eq(y, x + 1), Eq(y, 2 * x - 1)], [x, y])
assert I49 == {x: 2, y: 3}
bad = {0: solve(Eq(m + 1, 1), m), 1: solve(Eq(m + 1, 2), m), 2: solve(Eq(3, (m + 1) * 2 + m), m)}
assert bad == {0: [0], 1: [1], 2: [R(1, 3)]}
assert (0 != 1) and (1 != -1) and ((R(1, 3) + 1) * 2 + R(1, 3) == 3)

# 050: through M(4;1), a < 0; OA + OB = 5 + 4t + 1/t, t = -a > 0
tp = symbols("tp", positive=True)
S50 = 5 + 4 * tp + 1 / tp
assert simplify(S50 - 9 - (2 * tp - 1) ** 2 / tp) == 0
assert minimum(S50, tp, Interval.open(0, oo)) == 9 and S50.subs(tp, R(1, 2)) == 9
a50, b50 = -R(1, 2), 1 + 4 * R(1, 2)
assert b50 == 3 and a50 * 4 + b50 == 1 and solve(a50 * x + b50, x) == [6]
assert 1 - 4 * a50 == b50
# direct brute-force check of the formula OA + OB over sample slopes
for av in (-R(1, 4), -R(1, 3), -R(1, 2), -1, -2, -5):
    bv = 1 - 4 * av
    assert -bv / av + bv >= 9

# 051
xr = symbols("xr", real=True)
OM2 = xr**2 + (2 * xr + 3) ** 2
assert expand(OM2 - (5 * (xr + R(6, 5)) ** 2 + R(9, 5))) == 0
assert minimum(OM2, xr, S.Reals) == R(9, 5) and solve(OM2.diff(xr), xr) == [-R(6, 5)]
M51 = (-R(6, 5), 2 * (-R(6, 5)) + 3)
assert M51 == (-R(6, 5), R(3, 5)) and simplify(sqrt(R(9, 5)) - 3 * sqrt(5) / 5) == 0
A51, B51 = (0, 3), (solve(2 * x + 3, x)[0], 0)
assert B51 == (-R(3, 2), 0)
# OM orthogonal to direction (1, 2) of d  <=> M is the foot of the altitude from O
assert M51[0] * 1 + M51[1] * 2 == 0
# H = foot of altitude of the right triangle OAB: OH = OA*OB/AB
OH = 3 * R(3, 2) / sqrt(3**2 + R(3, 2) ** 2)
assert simplify(OH - sqrt(M51[0] ** 2 + M51[1] ** 2)) == 0

print("verify_8-ham-so-bac-nhat-2: all 20 OK")
