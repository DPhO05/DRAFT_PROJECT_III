"""Re-derive every boxed answer of bank-mo-rong/9-can-thuc-2.tex."""
from sympy import Abs, Interval, Rational as R, Symbol, cbrt, expand, factor, oo, radsimp, real_root, simplify, solve, sqrt
from sympy.solvers.inequalities import solve_univariate_inequality as sui

x = Symbol("x", real=True)
t = Symbol("t", positive=True)  # t = sqrt(x)
n = Symbol("n", real=True)
a, b = Symbol("a", real=True), Symbol("b", real=True)

def eq(u, v):
    return simplify(radsimp(u - v)) == 0

# 032
assert sqrt(121) - 3 * sqrt(R(4, 9)) == 9
assert sqrt((-9) ** 2) + sqrt(5) ** 2 == 14
assert 7 > sqrt(47) and 49 > 47

# 033
assert sui(x - 7 >= 0, x, relational=False) == Interval(7, oo)
assert sui(9 - 3 * x >= 0, x, relational=False) == Interval(-oo, 3)
assert sui(x**2 + 4 >= 0, x, relational=False) == Interval(-oo, oo)

# 034
assert sqrt(18) * sqrt(32) == 24
assert eq(sqrt(R(5, 2)) * sqrt(40), 10)
assert sqrt(17**2 - 8**2) == 15 and (17 - 8) * (17 + 8) == 9 * 25

# 035
assert 3 * sqrt(5) > 2 * sqrt(11) and 9 * 5 == 45 and 4 * 11 == 44
assert -4 * sqrt(3) < -3 * sqrt(5) and 16 * 3 == 48

# 036
assert eq(cbrt(24) - cbrt(81) + cbrt(375), 4 * cbrt(3))
assert real_root(24, 3) == 2 * real_root(3, 3) and real_root(81, 3) == 3 * real_root(3, 3) and real_root(375, 3) == 5 * real_root(3, 3)
assert real_root(-R(8, 125), 3) + real_root(R(8, 1000), 3) == R(-1, 5)

# 037
assert eq(10 / sqrt(5), 2 * sqrt(5))
assert eq(6 / (sqrt(7) - 1), sqrt(7) + 1)
assert eq(sqrt(2) / (sqrt(6) + sqrt(2)), (sqrt(3) - 1) / 2)

# 038
assert eq(sqrt(80), 4 * sqrt(5)) and eq(sqrt(45), 3 * sqrt(5))
assert eq(2 * (sqrt(80) + sqrt(45)), 14 * sqrt(5))
assert eq(sqrt(80) * sqrt(45), 60) and eq(sqrt(80 + 45), 5 * sqrt(5))

# 039
s39a = solve(sqrt(5 - x) - sqrt(2 * x - 1), x)
assert s39a == [2] and R(1, 2) <= 2 <= 5
assert sorted(solve(Abs(2 * x - 1) - 5, x)) == [-2, 3]
assert all(sqrt(4 * v**2 - 4 * v + 1) == 5 for v in (3, -2))
assert expand((2 * x - 1) ** 2 - (4 * x**2 - 4 * x + 1)) == 0

# 040
A40 = (t**2 - 9) / (t - 3) - (t**2 + 2 * t) / (t + 2)
assert simplify(A40) == 3
for v in (0, R(1, 4), 2, 5, 16, 100):
    sv = sqrt(v)
    assert eq((v - 9) / (sv - 3) - (v + 2 * sv) / (sv + 2), 3)

# 041
B41 = sqrt(x**2 - 2 * x + 1) + sqrt(x**2 + 6 * x + 9)
for v in (-3, -2, 0, R(1, 2), 1):
    assert B41.subs(x, v) == 4
for v in (2, 3, 7, R(3, 2)):
    assert B41.subs(x, v) == 2 * v + 2
assert expand((x - 1) ** 2 - (x**2 - 2 * x + 1)) == 0 and expand((x + 3) ** 2 - (x**2 + 6 * x + 9)) == 0

# 042: Heron
def heron(p1, p2, p3):
    p = R(p1 + p2 + p3, 2)
    return sqrt(p * (p - p1) * (p - p2) * (p - p3))
assert heron(13, 14, 15) == 84 and 21 * 8 * 7 * 6 == (2**2 * 3 * 7) ** 2
assert R(1, 2) * 14 * 12 == 84
assert eq(heron(7, 8, 9), 12 * sqrt(5)) and 12 * 5 * 4 * 3 == 720 == 12**2 * 5

# 043
f43 = sqrt(x**2 - 9) - 3 * sqrt(x - 3)
assert f43.subs(x, 3) == 0 and simplify(f43.subs(x, 6)) == 0
assert all(f43.subs(x, v) != 0 for v in (R(7, 2), 4, 5, 7, 10))  # no other root sampled in x >= 3
u = Symbol("u", nonnegative=True)  # u = sqrt(x-3): u*(sqrt(u^2+6) - 3) = 0
assert solve(u * (sqrt(u**2 + 6) - 3), u) == [0, sqrt(3)] and 3 + 3 == 6

# 044
assert eq(sqrt(11 - 6 * sqrt(2)), 3 - sqrt(2))
assert expand((3 - sqrt(2)) ** 2) == 11 - 6 * sqrt(2)
assert expand((2 + sqrt(3)) ** 2) == 7 + 4 * sqrt(3) and expand((sqrt(3) - 1) ** 2) == 4 - 2 * sqrt(3)
assert eq(sqrt(7 + 4 * sqrt(3)) - sqrt(4 - 2 * sqrt(3)), 3)

# 045
B45 = (1 / (t - 1) + 1 / (t + 1)) / ((t**2 + 1) / (t**2 - 1))
assert simplify(B45 - 2 * t / (t**2 + 1)) == 0
assert sorted(s for s in solve(2 * t / (t**2 + 1) - R(4, 5), t)) == [R(1, 2), 2]
assert factor(2 * t**2 - 5 * t + 2) == (2 * t - 1) * (t - 2)
assert [R(1, 2) ** 2, 2**2] == [R(1, 4), 4]
assert simplify(1 - 2 * t / (t**2 + 1) - (t - 1) ** 2 / (t**2 + 1)) == 0
assert all(2 * sqrt(v) / (v + 1) < 1 for v in (0, R(1, 4), 2, 3, 9, 100))

# 046
assert eq(4 / (sqrt(7) - sqrt(3)), sqrt(7) + sqrt(3))
assert expand((1 + sqrt(2)) ** 2 - 3) == 2 * sqrt(2)
assert eq(1 / (1 + sqrt(2) + sqrt(3)), (2 + sqrt(2) - sqrt(6)) / 4)
assert eq((1 + sqrt(2) - sqrt(3)) / (2 * sqrt(2)), (2 + sqrt(2) - sqrt(6)) / 4)

# 047
M = t**2 - 4 * t + 7
assert expand((t - 2) ** 2 + 3 - M) == 0 and M.subs(t, 2) == 3 and 2**2 == 4
assert solve(M.diff(t), t) == [2]
N = 1 / (t**2 - t + 1)
assert simplify((t**2 - t + 1) - ((t - R(1, 2)) ** 2 + R(3, 4))) == 0
assert N.subs(t, R(1, 2)) == R(4, 3) and R(1, 2) ** 2 == R(1, 4)
assert solve(N.diff(t), t) == [R(1, 2)]
assert all(N.subs(t, R(k, 20)) <= R(4, 3) for k in range(0, 200))

# 048
assert solve(sqrt(2 * x - 1) - (x - 2), x) == [5]
assert factor(x**2 - 6 * x + 5) == (x - 1) * (x - 5)
assert sqrt(2 * 1 - 1) == 1 and 1 - 2 == -1 and sqrt(2 * 5 - 1) == 3 == 5 - 2
assert solve(sqrt(x + 5) + sqrt(x - 3) - 4, x) == [4]
assert sqrt(9) + sqrt(1) == 4
assert expand((4 - sqrt(x - 3)) ** 2 - (16 - 8 * sqrt(x - 3) + x - 3)) == 0

# 049
u, v = Symbol("u", real=True), Symbol("v", real=True)
assert factor(u**3 - v**3) == (u - v) * (u**2 + u * v + v**2)
assert (125 - 27) / (25 + 15 + 9) == 2 and real_root(125, 3) - real_root(27, 3) == 2
assert real_root(125**2, 3) == 25 and real_root(125 * 27, 3) == 15 and real_root(27**2, 3) == 9
assert (27 - 8) / (9 + 6 + 4) == 1 and 3**3 == 27 and real_root(8, 3) == 2

# 050
P = (t**2 + 2) / (t**3 - 1) + (t + 1) / (t**2 + t + 1) - 1 / (t - 1)
assert simplify(P - t / (t**2 + t + 1)) == 0
assert factor(t**3 - 1) == (t - 1) * (t**2 + t + 1)
assert expand((t**2 + 2) + (t + 1) * (t - 1) - (t**2 + t + 1)) == t**2 - t
assert simplify(R(1, 3) - t / (t**2 + t + 1) - (t - 1) ** 2 / (3 * (t**2 + t + 1))) == 0
assert sorted(solve(t / (t**2 + t + 1) - R(3, 13), t)) == [R(1, 3), 3]
assert factor(3 * t**2 - 10 * t + 3) == (3 * t - 1) * (t - 3)
assert [R(1, 3) ** 2, 3**2] == [R(1, 9), 9]
for v in (R(1, 9), 9):
    assert eq(sqrt(v) / (v + sqrt(v) + 1), R(3, 13))
assert all(t0 / (t0**2 + t0 + 1) < R(1, 3) for t0 in (0, R(1, 2), 2, 3, 10) if t0 != 1)

# 051
assert all(eq((sqrt(v - 1) + sqrt(5 - v)) ** 2, 4 + 2 * sqrt((v - 1) * (5 - v))) for v in (1, R(3, 2), 2, 3, R(9, 2), 5))
assert expand((x - 1) + (5 - x)) == 4
assert expand((x - 1) * (5 - x) - (4 - (x - 3) ** 2)) == 0
y = sqrt(x - 1) + sqrt(5 - x)
vals = [y.subs(x, R(k, 8)) for k in range(8, 41)]
assert max(vals) == y.subs(x, 3) == 2 * sqrt(2)
assert min(vals) == y.subs(x, 1) == y.subs(x, 5) == 2
assert all(2 <= float(w) <= float(2 * sqrt(2)) + 1e-12 for w in vals)
print("CAN-2: all 20 answers verified")
