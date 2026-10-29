"""Re-derive every boxed answer of 9-ham-so-y-ax2.tex with sympy."""
from sympy import Abs, Rational as R, discriminant, expand, minimum, simplify, solve, sqrt, symbols, Interval, oo
from sympy import solveset, S, And

x, m, a, n, v = symbols("x m a n v", real=True)
roots = lambda e: set(solve(e, x))

# 001
f = lambda t: 2*t**2
assert (f(-3), f(R(1, 2)), simplify(f(sqrt(2)))) == (18, R(1, 2), 4)
assert roots(2*x**2 - 8) == {2, -2}
# 002
av = solve(a*(-2)**2 - 2, a)[0]
assert av == R(1, 2)
on = lambda px, py: simplify(av*px**2 - py) == 0
assert on(4, 8) and not on(-1, R(-1, 2)) and on(sqrt(6), 3)
# 003
f = lambda t: -R(1, 3)*t**2
assert 2*sqrt(2) < 3 and f(2*sqrt(2)) > f(3) and f(2*sqrt(2)) == R(-8, 3)
assert roots(f(x) + 3) == {3, -3}
# 004
c = m**2 - 2*m + 3
assert expand((m - 1)**2 + 2 - c) == 0 and minimum(c, m) == 2
# 005
xs = roots(x**2 - (x + 2))
assert xs == {-1, 2} and {(t, t**2) for t in xs} == {(-1, 1), (2, 4)} and all(t**2 == t + 2 for t in xs)
nv = solve(discriminant(x**2 - x - n, x), n)
assert nv == [R(-1, 4)]
t = roots(x**2 - x - nv[0])
assert t == {R(1, 2)} and R(1, 2)**2 == R(1, 4)
# 006
av = solve(a*4 + 2, a)[0]
assert av == R(-1, 2)
xs = roots(av*x**2 - (x - 4))
assert xs == {2, -4} and {(t, t - 4) for t in xs} == {(2, -2), (-4, -8)}
assert all(av*t**2 == t - 4 for t in xs)
# 007
p = x**2 - 2*x - m
d = discriminant(p, x) / 4
assert expand(d) == m + 1
assert solveset(d < 0, m, S.Reals) == Interval.open(-oo, -1)
cond = solveset(d > 0, m, S.Reals).intersect(solveset(-m > 0, m, S.Reals))
assert cond == Interval.open(-1, 0)
for mv in [R(-1, 2), R(-1, 10), R(-9, 10)]:
    r = solve(p.subs(m, mv), x)
    assert len(r) == 2 and all(t > 0 for t in r)
for mv in [0, R(1, 2), -1, R(-11, 10)]:
    r = solve(p.subs(m, mv), x)
    assert not (len(r) == 2 and all(t > 0 for t in r))
# 008
p = x**2 - 2*m*x + 2*m - 3
assert expand(discriminant(p, x) / 4 - ((m - 1)**2 + 2)) == 0
ms = solve(expand((2*m)**2 - 2*(2*m - 3)) - 14, m)
assert set(ms) == {-1, 2}
for mv in ms:
    r = solve(p.subs(m, mv), x)
    assert len(r) == 2 and simplify(r[0]**2 + r[1]**2 - 14) == 0
# 009
p = x**2 - m*x - 1
assert expand(discriminant(p, x)) == m**2 + 4
ms = set()
for mv in range(-10, 11):
    r = solve(p.subs(m, mv), x)
    assert r[0]*r[1] < 0
    if simplify(sum(t**2 for t in r) - 3*sum(r)) == 0:
        ms.add(mv)
assert ms == {1, 2} and set(solve(m**2 + 2 - 3*m, m)) == {1, 2}

def area(mv):
    x1, x2 = solve(p.subs(m, mv), x)
    A, B = (x1, x1**2), (x2, x2**2)
    return simplify(Abs(A[0]*B[1] - A[1]*B[0]) / 2)  # shoelace with O(0;0)

for mv in [0, 1, -3, R(1, 2)]:
    assert simplify(area(mv) - sqrt(mv**2 + 4)/2) == 0
assert area(0) == 1 and minimum(sqrt(m**2 + 4)/2, m) == 1
# 010
av = solve(a*2**2 - 120, a)[0]
assert av == 30 and av*10**2 == 3000
vv = R(90_000, 3_600)
assert vv == 25 and av*vv**2 == 18750 and 18750 > 12000
assert max(solve(av*v**2 - 12000, v)) == 20
# ---------------- 011..020
from sympy import Eq, maximum, discriminant, symbols as _sy
w, k, b, t = _sy("w k b t", real=True)

# 011
g = lambda u: -R(1, 2)*u**2
assert [g(u) for u in (-4, -2, 0, 2, 4)] == [-8, -2, 0, -2, -8]
assert maximum(g(x), x) == 0

# 012
assert solveset(2*m - 3 > 0, m, S.Reals) == Interval.open(R(3, 2), oo)
m12 = solve(Eq(-6, (2*m - 3)*(-2)**2), m)
assert m12 == [R(3, 4)] and 2*m12[0] - 3 == R(-3, 2)

# 013
assert 5*3**2 == 45
assert [s for s in solve(5*t**2 - 125, t) if s > 0] == [5]
assert 125 - 5*2**2 == 105

# 014
h = lambda u: R(1, 2)*u**2
A, B = (-2, h(-2)), (4, h(4))
assert A == (-2, 2) and B == (4, 8)
s14 = solve([Eq(A[1], a*A[0] + b), Eq(B[1], a*B[0] + b)], [a, b])
assert s14 == {a: 1, b: 4}
assert solve([Eq(-2 + 4, 2*a), Eq(-2*4, -2*b)], [a, b]) == {a: 1, b: 4}   # cach 2 (Viete)

# 015
mp = _sy("mp", positive=True)
xs = solve(x**2 - mp, x)
assert set(xs) == {-sqrt(mp), sqrt(mp)}
OA2 = mp**2 + mp; AB2 = 4*mp
assert solve(Eq(2*OA2, AB2), mp) == [1] and solve(Eq(mp, sqrt(mp)), mp) == [1]
assert R(1, 2)*2*1 == 1

# 016
p16 = x**2 - (m + 1)*x + m
assert set(solve(p16, x)) == {1, m} and expand(discriminant(p16, x) - (m - 1)**2) == 0
assert solve(discriminant(p16, x), m) == [1]
ms = set()
for mv in [R(n, 4) for n in range(-40, 41)]:
    r = solve(p16.subs(m, mv), x)
    if len(r) == 2 and (r[0] == 2*r[1] or r[1] == 2*r[0]):
        ms.add(mv)
assert ms == {2, R(1, 2)}, ms

# 017
p17 = x**2 - k*x + k + 3                       # line y = kx - k - 3 through (1; -3)
ks = solve(discriminant(p17, x), k)
assert set(ks) == {6, -2}
for kv, bv, tp in [(6, -9, (3, 9)), (-2, -1, (-1, 1))]:
    assert -kv - 3 == bv and kv*1 + bv == -3
    r = solve(p17.subs(k, kv), x)
    assert r == [tp[0]] and tp[0]**2 == tp[1]

# 018
p18 = x**2 - 2*x + m - 3
assert expand(discriminant(p18, x)/4) == 4 - m
assert solveset(4 - m > 0, m, S.Reals) == Interval.open(-oo, 4)
r = solve(p18.subs(m, -2), x)
assert len(r) == 2
for x1, x2 in [(r[0], r[1]), (r[1], r[0])]:
    assert simplify(x1**2 + 2*x2 - 9) == 0
mm = solve(Eq(7 - m, 9), m)
assert mm == [-2]
# general: y1 + 2x2 = 7 - m for both orderings, symbolic
x1s, x2s = solve(p18, x)
for u, v in [(x1s, x2s), (x2s, x1s)]:
    assert simplify(expand(u**2 + 2*v) - (7 - m)) == 0

# 019
av = solve(Eq(-8, a*4**2), a)[0]
assert av == R(-1, 2)
height = lambda u: av*u**2 + 8
assert height(3) == R(7, 2) and height(3) < 4
wmax = max(solve(Eq(height(w/2), 6), w))
assert wmax == 4 and height(R(4, 2)) == 6
assert solveset(height(w/2) >= 6, w, S.Reals).intersect(Interval.open(0, oo)) == Interval.Lopen(0, 4)

# 020
p20 = x**2 - 4*m*x - 4
assert expand(discriminant(p20, x)/4) == 4*m**2 + 4
for mv in [0, 1, -1, 2, R(1, 3)]:
    x1, x2 = solve(p20.subs(m, mv), x)
    y1, y2 = mv*x1 + 1, mv*x2 + 1
    assert simplify(x1**2/4 - y1) == 0 and simplify(x2**2/4 - y2) == 0
    AB = sqrt((x1 - x2)**2 + (y1 - y2)**2)
    assert simplify(AB - 4*(mv**2 + 1)) == 0
    assert simplify(AB - (y1 + y2 + 2)) == 0
assert set(solve(Eq(4*(m**2 + 1), 8), m)) == {1, -1}

# ---------------- 021..031

# 021
coef = {"3x^2": 3, "-2/5x^2": R(-2, 5), "(1-sqrt2)x^2": 1 - sqrt(2), "1/4x^2": R(1, 4)}
assert {k for k, c in coef.items() if c > 0} == {"3x^2", "1/4x^2"}
assert {k for k, c in coef.items() if c < 0} == {"-2/5x^2", "(1-sqrt2)x^2"}
for c in coef.values():   # a > 0 <=> increasing for x > 0 (check on 1 < 2)
    assert (c*2**2 > c*1**2) == (c > 0)

# 022
P = lambda u: -R(1, 2)*u**2
xs = roots(P(x) - (x - R(3, 2)))
assert xs == {1, -3} and {(u, u - R(3, 2)) for u in xs} == {(1, R(-1, 2)), (-3, R(-9, 2))}
assert all(P(u) == u - R(3, 2) for u in xs)
xs = solve(P(x) - (2*x + 2), x)
assert xs == [-2] and P(-2) == -2 == 2*(-2) + 2 and expand(-2*(P(x) - 2*x - 2) - (x + 2)**2) == 0
assert solve(P(x) - 1, x) == []

# 023
a23 = solve(Eq(-1, a*(-2)**2), a)[0]
assert a23 == R(-1, 4)
assert [a23*u**2 for u in (-4, -2, 0, 2, 6)] == [-4, -1, 0, -1, -9]
xs = roots(a23*x**2 - (-x - 3))
assert xs == {6, -2} and {(u, -u - 3) for u in xs} == {(6, -9), (-2, -1)}
assert [u for u in (-4, -2, 0, 2, 6) if a23*u**2 == -u - 3] == [-2, 6]

# 024
yA = -(-2) + 6
a24 = solve(Eq(yA, a*(-2)**2), a)[0]
assert yA == 8 and a24 == 2
xs = roots(a24*x**2 - (-x + 6))
assert xs == {-2, R(3, 2)} and R(-6, 2)/(-2) == R(3, 2)
assert -R(3, 2) + 6 == R(9, 2) == a24*R(3, 2)**2


# 025
f25 = lambda u: -2*u**2
assert (maximum(f25(x), x, Interval(1, 3)), minimum(f25(x), x, Interval(1, 3))) == (-2, -18)
assert (maximum(f25(x), x, Interval(-1, 2)), minimum(f25(x), x, Interval(-1, 2))) == (0, -8)
assert f25(1) == -2 and f25(3) == -18 and f25(0) == 0 and f25(2) == -8 and f25(-1) == -2

# 026
b26 = solve(Eq(1, 2*1 + b), b)[0]
assert b26 == -1 and b26 != 5
xs = roots(-x**2 - (2*x + b26))
assert xs == {-1 + sqrt(2), -1 - sqrt(2)}
for u, yv in [(-1 + sqrt(2), -3 + 2*sqrt(2)), (-1 - sqrt(2), -3 - 2*sqrt(2))]:
    assert simplify(2*u - 1 - yv) == 0 and simplify(-u**2 - yv) == 0

# 027  points of y = x^2/3, not O, with |y| = |x|
pts = {(u, u**2/3) for u in solve(x**2/3 - Abs(x), x) if u != 0}
assert pts == {(3, 3), (-3, 3)}
assert {u for u in roots(x**2/3 - x)} | {u for u in roots(x**2/3 + x)} == {0, 3, -3}   # cach 2

# 028  f(-3) > f(2) <=> a > 0
assert solveset(9*a - 4*a > 0, a, S.Reals) == Interval.open(0, oo)
assert 0 < 1 + sqrt(2) < 2*sqrt(2) and (1 + sqrt(2))**2 < 8
for av in [R(1, 5), 1, 7]:        # any a > 0
    g = lambda u: av*u**2
    assert g(1 + sqrt(2)) < g(-2*sqrt(2))
    assert solveset(g(x) < g(3), x, S.Reals) == Interval.open(-3, 3)


# 029
c29 = m**2 - 4*m + 3
assert expand((m - 1)*(m - 3) - c29) == 0
assert solveset(c29 > 0, m, S.Reals) == Interval.open(-oo, 1) | Interval.open(3, oo)
assert solveset(c29 < 0, m, S.Reals) == Interval.open(1, 3)
assert solveset(m - 1 < 0, m, S.Reals).intersect(solveset(m - 3 > 0, m, S.Reals)) == S.EmptySet
mi = [k for k in range(-20, 21) if k not in (1, 3) and c29.subs(m, k) < 0]
assert mi == [2] and c29.subs(m, 2) == -1 and -(-3)**2 == -9

# 030
xs = roots(-x**2/20 - (-x/2 - 10))
assert xs == {20, -10}
xT = [u for u in xs if u > 0][0]
assert (xT, -xT/2 - 10) == (20, -20) and -R(1, 20)*20**2 == -20
C = (0, -10)
assert simplify(sqrt((20 - C[0])**2 + (-20 - C[1])**2) - 10*sqrt(5)) == 0
yT2 = -R(30, 2) - 10
assert yT2 == -25 and solve(Eq(yT2, a*30**2), a) == [R(-1, 36)]

# 031
xs = roots(x**2 - (x + 6))
assert xs == {-2, 3}
A, B = (-2, 4), (3, 9)
assert all(u**2 == u + 6 for u in xs)
assert simplify(sqrt((B[0] - A[0])**2 + (B[1] - A[1])**2) - 5*sqrt(2)) == 0
tri = lambda P1, P2, P3: Abs((P2[0] - P1[0])*(P3[1] - P1[1]) - (P3[0] - P1[0])*(P2[1] - P1[1])) / 2
assert tri((0, 0), A, B) == 15
cc = symbols("cc", real=True)
S31 = R(5, 2)*(6 + cc - cc**2)
for cv in [R(-3, 2), 0, R(1, 2), 1, R(5, 2)]:
    assert tri(A, B, (cv, cv**2)) == S31.subs(cc, cv)
assert expand(6 + cc - cc**2 - (R(25, 4) - (cc - R(1, 2))**2)) == 0
assert maximum(S31, cc, Interval.open(-2, 3)) == R(125, 8)
assert solve(S31.diff(cc), cc) == [R(1, 2)] and R(1, 2)**2 == R(1, 4)

print("HSB2: all 31 problems verified")
