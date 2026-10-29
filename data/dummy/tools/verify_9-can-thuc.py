"""Re-derive every boxed answer of 9-can-thuc.tex."""
from sympy import Abs, Interval, Rational as R, Symbol, cbrt, expand, factor, oo, radsimp, real_root, simplify, solve, sqrt, sstr
from sympy.solvers.inequalities import solve_univariate_inequality as sui

x = Symbol("x", real=True)
t = Symbol("t", nonnegative=True)  # t = sqrt(x)
a = Symbol("a", negative=True)

def eq(u, v):
    return simplify(radsimp(u - v)) == 0

# 001: ĐKXĐ
assert sui(2 * x - 6 >= 0, x, relational=False) == Interval(3, oo)
assert sui(10 - 5 * x >= 0, x, relational=False) == Interval(-oo, 2)

# 002
assert eq(sqrt((2 - sqrt(5)) ** 2) + sqrt((3 - sqrt(5)) ** 2), 1)

# 003
assert sqrt(12) * sqrt(75) == 30
assert sqrt(63) / sqrt(7) - sqrt(R(16, 81)) == R(23, 9)

# 004
assert eq(2 * sqrt(12) - 3 * sqrt(27) + sqrt(75) + R(1, 2) * sqrt(48), 2 * sqrt(3))
assert eq(sqrt(18 * a**2), -3 * a * sqrt(2))
vals = {"5r2": 5 * sqrt(2), "4r3": 4 * sqrt(3), "3r6": 3 * sqrt(6), "2r13": 2 * sqrt(13)}
assert sorted(vals, key=lambda k: float(vals[k])) == ["4r3", "5r2", "2r13", "3r6"]
assert [v**2 for v in (4 * sqrt(3), 5 * sqrt(2), 2 * sqrt(13), 3 * sqrt(6))] == [48, 50, 52, 54]

# 005
assert eq(6 / sqrt(3) + 2 / (sqrt(3) - 1) - 4 / (sqrt(3) + 1), 3 + sqrt(3))
k = Symbol("k", positive=True)
assert eq(1 / (sqrt(k) + sqrt(k + 1)), sqrt(k + 1) - sqrt(k))  # conjugate step
assert sum(sqrt(j + 1) - sqrt(j) for j in range(1, 100)) == 9  # telescoping
assert abs(sum(1 / (j**0.5 + (j + 1) ** 0.5) for j in range(1, 100)) - 9) < 1e-12

# 006
assert real_root(54, 3) * real_root(4, 3) - real_root(-125, 3) + real_root(81, 3) / real_root(3, 3) == 14
assert 2**3 * 3 == 24 and float(2 * cbrt(3)) > float(cbrt(23))
assert solve(2 * x - 1 - (-3) ** 3, x) == [-13] and real_root(2 * (-13) - 1, 3) == -3

# 007: P with t = sqrt(x)
P = 2 * t / (t + 3) + (t + 1) / (t - 3) + (7 * t + 3) / (9 - t**2)
assert simplify(P - 3 * t / (t + 3)) == 0
assert expand(2 * t * (t - 3) + (t + 1) * (t + 3) - (7 * t + 3)) == 3 * t**2 - 9 * t
xv = 4 - 2 * sqrt(3)
assert eq(sqrt(xv), sqrt(3) - 1)
assert eq(3 * sqrt(xv) / (sqrt(xv) + 3), 9 * sqrt(3) - 15)
assert eq(P.subs(t, sqrt(3) - 1), 9 * sqrt(3) - 15)  # original (unsimplified) form
for xn in (0, R(1, 4), 2, 5, 16, 100):  # numeric spot-check on original P
    tn = sqrt(xn)
    assert abs(float(P.subs(t, tn)) - float(3 * tn / (tn + 3))) < 1e-12

# 008: sqrt(4x-8) + 1/3 sqrt(9x-18) - sqrt(x-2) = 4, x >= 2
f8 = sqrt(4 * x - 8) + R(1, 3) * sqrt(9 * x - 18) - sqrt(x - 2) - 4
u = Symbol("u", nonnegative=True)  # u = sqrt(x-2)
assert expand(sqrt(4) * u + R(1, 3) * sqrt(9) * u - u) == 2 * u and solve(2 * u - 4, u) == [2]
assert 2**2 + 2 == 6 and f8.subs(x, 6) == 0

# 009: sqrt(x^2-6x+9) = 2x-3
f9 = sqrt(x**2 - 6 * x + 9) - (2 * x - 3)
assert solve(x**2 - 6 * x + 9 - (2 * x - 3) ** 2, x) == [0, 2]  # squaring: 0 is extraneous
assert f9.subs(x, 0) != 0 and f9.subs(x, 2) == 0
assert factor(x**2 - 6 * x + 9 - (2 * x - 3) ** 2) == -3 * x * (x - 2)

# 010: Q with t = sqrt(x)
Q = t / (t - 1) + 3 / (t + 1) - (6 * t - 4) / (t**2 - 1)
assert simplify(Q - (t - 1) / (t + 1)) == 0
assert expand(t * (t + 1) + 3 * (t - 1) - (6 * t - 4)) == expand((t - 1) ** 2)
assert solve((t - 1) / (t + 1) - R(1, 3), t) == [2]  # sqrt(x)=2 -> x=4
for xn in (0, R(1, 9), 2, 4, 9, 50):
    tn = sqrt(xn)
    assert abs(float(Q.subs(t, tn)) - float((tn - 1) / (tn + 1))) < 1e-12
# integer values: Q in [-1, 1); Q=-1 at x=0, Q=0 at x=1 (excluded)
assert simplify((t - 1) / (t + 1) - (1 - 2 / (t + 1))) == 0
assert ((t - 1) / (t + 1)).subs(t, 0) == -1
assert solve((t - 1) / (t + 1), t) == [1]  # x = 1, excluded
assert solve((t - 1) / (t + 1) + 1, t) == [0]  # x = 0
import random
random.seed(2)
for _ in range(2000):
    xn = random.uniform(0, 1e4)
    q = (xn**0.5 - 1) / (xn**0.5 + 1)
    assert -1 <= q < 1


# ---------------------------------------------------------------- 011..020
from sympy import Interval as I_, maximum, sqrtdenest, symbols
from sympy.solvers.inequalities import solve_univariate_inequality as sui2

# 011
assert set(solve(x**2 - R(121, 4), x)) == {R(11, 2), R(-11, 2)} and sqrt(R(121, 4)) == R(11, 2)
assert solve(sqrt(t) - R(2, 3), t) == [R(4, 9)]
assert solve(sqrt(t) + 5, t) == []

# 012: t = sqrt(h/5)
h = Symbol("h", positive=True)
assert sqrt(R(125, 5)) == 5
assert solve(sqrt(h / 5) - 3, h) == [45]
assert simplify(sqrt(4 * h / 5) / sqrt(h / 5)) == 2

# 013
a0 = Symbol("a0", nonnegative=True)
ap = Symbol("ap", positive=True)
b = Symbol("b", real=True)
xneg = Symbol("xneg", negative=True)
ypos = Symbol("ypos", positive=True)
assert simplify(sqrt(2 * a0) * sqrt(8 * a0**3) - 4 * a0**2) == 0
assert simplify(sqrt(45 * ap * b**4) / sqrt(5 * ap) - 3 * b**2) == 0
assert simplify(sqrt(25 * xneg**2 / ypos**6) + 5 * xneg / ypos**3) == 0
for av, bv in ((R(1, 3), -2), (2, R(3, 2)), (5, 0)):  # numeric spot-check
    assert abs(float(sqrt(2 * av) * sqrt(8 * av**3)) - 4 * av**2) < 1e-9
    assert abs(float(sqrt(45 * av * bv**4) / sqrt(5 * av)) - 3 * bv**2) < 1e-9
assert abs(float(sqrt(25 * R(-3, 2) ** 2 / R(2) ** 6)) - float(-5 * R(-3, 2) / 2**3)) < 1e-12

# 014
A14 = sqrt(8 - 2 * sqrt(7)) - sqrt(8 + 2 * sqrt(7))
assert expand((sqrt(7) - 1) ** 2) == 8 - 2 * sqrt(7) and expand((sqrt(7) + 1) ** 2) == 8 + 2 * sqrt(7)
assert simplify(sqrtdenest(A14) + 2) == 0 and abs(float(A14) + 2) < 1e-12
assert expand((8 - 2 * sqrt(7)) * (8 + 2 * sqrt(7))) == 36 and 16 - 2 * 6 == 4

# 015
assert abs(float(real_root(float((1 - sqrt(2)) ** 3), 3)) - float(1 - sqrt(2))) < 1e-12
assert eq((1 - sqrt(2)) + Abs(1 - sqrt(2)), 0)
assert expand((x + 2) ** 3) == x**3 + 6 * x**2 + 12 * x + 8
assert solve(x**3 - 6 * x**2 + 19 - (x - 2) ** 3, x) == [R(9, 4)]
xv15 = R(9, 4)
assert xv15**3 - 6 * xv15**2 + 19 == R(1, 64) and real_root(R(1, 64), 3) == xv15 - 2

# 016: sqrt(x^2-x-3) = sqrt(2x+1)
cand16 = solve(x**2 - x - 3 - (2 * x + 1), x)
assert set(cand16) == {-1, 4}
assert [c for c in cand16 if 2 * c + 1 >= 0 and c**2 - c - 3 >= 0] == [4]
assert (sqrt(x**2 - x - 3) - sqrt(2 * x + 1)).subs(x, 4) == 0
assert factor(x**2 - 3 * x - 4) == (x - 4) * (x + 1)

# 017: identity with a = p^2, b = q^2
p_, q_ = symbols("p q", positive=True)
lhs17 = (p_**2 * p_ + q_**2 * q_) / (p_ + q_) - p_ * q_
assert simplify(lhs17 - (p_ - q_) ** 2) == 0
for av, bv in ((2, 3), (R(1, 5), 7), (9, 9)):
    l = (av * sqrt(av) + bv * sqrt(bv)) / (sqrt(av) + sqrt(bv)) - sqrt(av * bv)
    assert abs(float(l) - float((sqrt(av) - sqrt(bv)) ** 2)) < 1e-12

# 018: t = sqrt(x) > 0, t != 2
tp = Symbol("tp", positive=True)
P18 = (2 / (tp**2 - 2 * tp) + 1 / (tp - 2)) / ((tp + 2) / (tp**2 - 4 * tp + 4))
assert simplify(P18 - (tp - 2) / tp) == 0
assert simplify((tp - 2) / tp - 1 + 2 / tp) == 0  # P - 1 = -2/sqrt(x) < 0
assert sui2((tp - 2) / tp > R(1, 2), tp, relational=False).intersect(I_.open(0, oo)) == I_.open(4, oo)  # sqrt(x) > 4 <=> x > 16
for xn in (R(1, 4), 1, 9, 16, 17, 100):  # original form vs boxed, and P > 1/2 iff x > 16
    v = float(P18.subs(tp, sqrt(xn)))
    assert abs(v - float((sqrt(xn) - 2) / sqrt(xn))) < 1e-12 and v < 1
    assert (v > 0.5) == (xn > 16)

# 019
X19 = real_root(9 + 4 * sqrt(5), 3) + real_root(9 - 4 * sqrt(5), 3)
assert abs(float(X19) - 3) < 1e-12
assert expand(((3 + sqrt(5)) / 2) ** 3) == 9 + 4 * sqrt(5) and expand(((3 - sqrt(5)) / 2) ** 3) == 9 - 4 * sqrt(5)
assert expand((3 + sqrt(5)) ** 3) == 72 + 32 * sqrt(5)
assert expand((9 + 4 * sqrt(5)) * (9 - 4 * sqrt(5))) == 1
assert expand((x - 3) * (x**2 + 3 * x + 6)) == x**3 - 3 * x - 18
assert solve(x**3 - 3 * x - 18, x) == [3]  # x real: other factor has no real root
assert expand((x + R(3, 2)) ** 2 + R(15, 4)) == x**2 + 3 * x + 6

# 020: t = sqrt(x) >= 0
P20 = (2 * t**2 + 1) / (t**3 + 1) - 1 / (t + 1)
R20 = t / (t**2 - t + 1)
assert simplify(P20 - R20) == 0
assert simplify(1 - R20 - (t - 1) ** 2 / (t**2 - t + 1)) == 0
assert maximum(R20, t, I_(0, oo)) == 1 and R20.subs(t, 1) == 1
assert R20.subs(t, 0) == 0 and solve(R20, t) == [0] and solve(R20 - 1, t) == [1]
random.seed(20)
for _ in range(2000):
    tn = random.uniform(0, 100) ** 0.5
    pv = (2 * tn**2 + 1) / (tn**3 + 1) - 1 / (tn + 1)
    assert -1e-12 <= pv <= 1 + 1e-12

# ---- 021..031
from sympy import Union, cancel, nsimplify
from sympy import Symbol as Sym_

# 021
assert sqrt(36 * 225) == 90 and sqrt(36) * sqrt(225) == 90
assert R(2 * 25 + 14, 25) == R(64, 25) and sqrt(R(64, 25)) == R(8, 5)

# 022
assert solve((3 * x + 1) / (x + 2) - 4, x) == [-7]
assert ((3 * x + 1) / (x + 2)).subs(x, -7) == 4
assert sqrt((3 * x + 1) / (x + 2)).subs(x, -7) == 2
dom22b = sui(3 * x + 1 >= 0, x, relational=False).intersect(sui(x + 2 > 0, x, relational=False))
assert dom22b == Interval(R(-1, 3), oo) and -7 not in dom22b
assert not sqrt(3 * x + 1).subs(x, -7).is_real  # only candidate -7 leaves the real domain of b)

# 023
assert sqrt(72) == 6 * sqrt(2) and sqrt(32) == 4 * sqrt(2)
assert 4 * sqrt(72) + 4 * sqrt(32) == 40 * sqrt(2)
assert expand((sqrt(72) + sqrt(32)) ** 2) == 200 and 200 - (72 + 32) == 96

# 024
ap = Sym_("ap", positive=True)
xn, yn = Sym_("xn", negative=True), Sym_("yn", negative=True)
assert eq(sqrt(R(5, 12)), sqrt(15) / 6)
assert simplify(sqrt(3 / (2 * ap**3)) - sqrt(6 * ap) / (2 * ap**2)) == 0
for xv, yv in [(-1, -2), (-3, -5), (R(-1, 2), -7), (-9, R(-2, 3))]:
    assert eq(xv * yv * sqrt(R(xv) / yv), -xv * sqrt(xv * yv))

# 025: M = (x-3) sqrt(2/(x^2-3x))
M25 = (x - 3) * sqrt(2 / (x**2 - 3 * x))
assert sui(x**2 - 3 * x > 0, x, relational=False) == Union(Interval.open(-oo, 0), Interval.open(3, oo))
assert simplify((x - 3) ** 2 * 2 / (x * (x - 3)) - 2 * (x - 3) / x) == 0
for xv in [R(7, 2), 4, 10, 100]:
    assert eq(M25.subs(x, xv), sqrt(2 * (xv - 3) / R(xv)))
for xv in [-1, R(-1, 3), -6, -50]:
    assert eq(M25.subs(x, xv), -sqrt(2 * (xv - 3) / R(xv)))
assert solve(2 * (x - 3) / x - 3, x) == [-6]
assert eq(M25.subs(x, -6), -sqrt(3))

# 026 (reduced eq sqrt(x-3)=3 differs from 008's sqrt(x-2)=2)
f26 = sqrt(4 * x**3 - 12 * x**2) + sqrt(x**3 - 3 * x**2) - 9 * x
assert sui(x**2 * (x - 3) >= 0, x, relational=False) == Union({0}, Interval(3, oo))
assert f26.subs(x, 0) == 0 and f26.subs(x, 12) == 0
assert 4 * 1728 - 12 * 144 == 5184 == 72**2 and 1728 - 432 == 1296 == 36**2 and 72 + 36 == 108
assert solve(sqrt(x - 3) - 3, x) == [12]
for k in range(1, 400):  # x >= 3: f26 = 3x(sqrt(x-3) - 3), zero only at 12
    xv = 3 + R(k, 4)
    if xv != 12:
        assert abs(float(f26.subs(x, xv))) > 1e-9

# 027
a27, b27 = 2 / (sqrt(5) - sqrt(3)), 2 / (sqrt(5) + sqrt(3))
assert eq(a27, sqrt(5) + sqrt(3)) and eq(b27, sqrt(5) - sqrt(3))
assert eq(a27 + b27, 2 * sqrt(5)) and eq(a27 * b27, 2) and eq(a27**2 + b27**2, 16)

# 028
A28 = sqrt(2030) - sqrt(2029)
B28 = sqrt(2029) - sqrt(2028)
assert (A28 - B28).evalf(60) < 0
assert 2030 * 2028 == 2029**2 - 1 and 4 * 2029 - 4058 == 4058

# 029
c3, c2 = real_root(3, 3), real_root(2, 3)
assert expand((c3 - 1) * (c3**2 + c3 + 1)) == 2
assert abs((2 / (c3 - 1) - (real_root(9, 3) + c3 + 1)).evalf(60)) < 1e-50
uu, vv = Sym_("uu"), Sym_("vv")
assert expand((uu - vv) * (uu**2 + uu * vv + vv**2)) == uu**3 - vv**3 and c3**3 - c2**3 == 1
assert (c3 - c2).evalf(30) > 0  # u - v != 0
assert abs(((c3 - c2) * (c3**2 + c3 * c2 + c2**2) - 1).evalf(60)) < 1e-50
assert abs((1 / (real_root(9, 3) + real_root(6, 3) + real_root(4, 3)) - (c3 - c2)).evalf(60)) < 1e-50

# 030
S30 = sum(1 / sqrt(k) for k in range(1, 101))
assert 18 < S30.evalf(50) < 19
assert (2 * sqrt(101) - 2).evalf(30) > 18
for k in range(1, 101):
    assert 1 / sqrt(k) > (2 * (sqrt(k + 1) - sqrt(k))).evalf(40)
    if k >= 2:
        assert 1 / sqrt(k) < (2 * (sqrt(k) - sqrt(k - 1))).evalf(40)

# 031
assert real_root(1728, 3) == 12 and 1728 + 1647 == 3375 and real_root(3375, 3) == 15
assert 15 - 12 == 3 and 15 > 0

print("verify_9-can-thuc: all 31 OK")
