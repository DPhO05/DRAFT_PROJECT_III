"""Re-derive every boxed answer of 9-phuong-trinh-bac-hai.tex with sympy."""
from sympy import Rational as R, S, discriminant, expand, simplify, solve, solveset, sqrt, symbols, minimum

x, m, X, u, v = symbols("x m X u v", real=True)
roots = lambda e: set(solve(e, x))

# 001
assert roots(3*x**2 - 12*x) == {0, 4}
assert roots(2*x**2 - 18) == {3, -3}
assert roots(5*x**2 + 20) == set()
# 002
e = x*(2*x - 3) - (2*(x + 1) + 1)
assert expand(e) == 2*x**2 - 5*x - 3 and discriminant(expand(e), x) == 49
assert roots(e) == {3, R(-1, 2)}
# 003
assert discriminant(x**2 - 6*x + 4, x) / 4 == 5 and roots(x**2 - 6*x + 4) == {3 + sqrt(5), 3 - sqrt(5)}
assert discriminant(9*x**2 - 12*x + 4, x) == 0 and roots(9*x**2 - 12*x + 4) == {R(2, 3)}
assert discriminant(2*x**2 + 3*x + 5, x) == -31 and roots(2*x**2 + 3*x + 5) == set()
# 004
assert roots(5*x**2 - 7*x + 2) == {1, R(2, 5)}
assert roots(2026*x**2 + 2025*x - 1) == {-1, R(1, 2026)}
# 005
p = x**2 - 5*x + 3
assert discriminant(p, x) == 13
x1, x2 = solve(p, x)
assert simplify(x1**2 + x2**2) == 19 and simplify(1/x1 + 1/x2) == R(5, 3) and simplify(x1**3 + x2**3) == 80
# 006
assert set(solve(X**2 - 17*X + 72, X)) == {8, 9}
assert {tuple(s) for s in solve([u - v - 3, u*v - 40], [u, v])} == {(8, 5), (-5, -8)}
assert discriminant(X**2 - 3*X + 5, X) == -11 and solve(X**2 - 3*X + 5, X) == []
# 007
p = x**2 - 2*(m + 1)*x + m**2 + 3
assert expand(discriminant(p, x) / 4) == 2*m - 2
assert expand((2*(m + 1))**2 - 2*(m**2 + 3)) == 2*m**2 + 8*m - 2
cand = solve(2*m**2 + 8*m - 2 - 22, m)
assert set(cand) == {2, -6}
ok = [c for c in cand if discriminant(p.subs(m, c), x) >= 0]
assert ok == [2]
r = solve(p.subs(m, 2), x)
assert len(r) == 2 and simplify(r[0]**2 + r[1]**2) == 22
assert discriminant(p.subs(m, -6), x) / 4 == -14
# 008
p = x**2 - m*x + m - 1
assert expand(discriminant(p, x) - (m - 2)**2) == 0
assert set(solve(2*m**2 - 9*m + 9, m)) == {3, R(3, 2)}
found = set()
for mv in [R(k, 4) for k in range(-40, 41)]:
    r = solve(p.subs(m, mv), x)
    r = r if len(r) == 2 else r * 2
    if any(simplify(a - 2*b) == 0 for a, b in [(r[0], r[1]), (r[1], r[0])]):
        found.add(mv)
assert found == {3, R(3, 2)}, found
# 009
p = x**2 - 2*(m + 1)*x + 2*m
assert expand(discriminant(p, x) / 4) == m**2 + 1
for mv in solve(2*m**2 + 3*m - 2, m):
    r = solve(p.subs(m, mv), x)
    for a, b in [(r[0], r[1]), (r[1], r[0])]:
        assert simplify(a**2 + 2*(mv + 1)*b - 8) == 0
assert set(solve(2*m**2 + 3*m - 2, m)) == {R(1, 2), -2}
A = expand((2*(m + 1))**2 - 2*2*m)
assert A == 4*m**2 + 4*m + 4 and expand((2*m + 1)**2 + 3 - A) == 0
assert minimum(A, m) == 3 and solve(A - 3, m) == [R(-1, 2)]
# 010
xs = solve(120/x - 120/(x + 10) - 1, x)
assert set(xs) == {30, -40} and [s for s in xs if s > 0] == [30]
assert R(120, 30) - R(120, 40) == 1

# ---------------------------------------------------------------- 011..020
y, T = symbols("y T", real=True)
rp = symbols("rp", positive=True)
fl = lambda e: float(e)

# 011
assert expand((x - 1)*(x + 1) - (2*x**2 - 10)) == -x**2 + 9 and roots((x - 1)*(x + 1) - (2*x**2 - 10)) == {3, -3}
assert expand((x + 3)**2 - (9 - 2*x)) == x**2 + 8*x and roots((x + 3)**2 - (9 - 2*x)) == {0, -8}
# 012
assert set(solve(100000000*(1 + x)**2 - 112360000, x)) == {R(6, 100), R(-206, 100)}
assert solve(100000000*(1 + rp)**2 - 112360000, rp) == [R(6, 100)] and 106**2 == 11236
assert 100000000 * R(106, 100) == 106000000 and 106000000 * R(106, 100) == 112360000
# 013
p = x**2 - (m + 2)*x + 2*m + 4
assert solve(p.subs(x, 3), m) == [7] and roots(p.subs(m, 7)) == {3, 6}
assert discriminant(p.subs(m, 7), x) == 9
# 014
assert set(solve(T**2 - 5*T - 36, T)) == {9, -4}
assert roots(x**4 - 5*x**2 - 36) == {3, -3}  # x real
# 015
f = x/(x - 1) + 2/(x + 1) - 2/(x**2 - 1)
assert expand(x*(x + 1) + 2*(x - 1) - 2) == x**2 + 3*x - 4 and roots(x**2 + 3*x - 4) == {1, -4}
assert solve(f, x) == [-4] and f.subs(x, -4) == 0
# 016
x1, x2 = solve(x**2 - 3*x - 5, x)
assert simplify(x1*x2) == -5
y1, y2 = x1 + 1/x2, x2 + 1/x1
assert simplify(y1 + y2) == R(12, 5) and simplify(y1*y2) == R(-16, 5)
assert all(simplify((5*y**2 - 12*y - 16).subs(y, v)) == 0 for v in (y1, y2))
# 017
p = x**2 - 2*(m - 3)*x + m - 5
assert roots(p.subs(m, 4)) == {1 + sqrt(2), 1 - sqrt(2)}
for mv in [R(k, 4) for k in range(-60, 61)]:
    r = [fl(s) for s in solve(p.subs(m, mv), x)]
    ok = len(r) == 2 and min(r) < 0 < max(r) and abs(min(r)) > max(r)
    assert ok == (mv < 3), mv
# 018
p = x**2 - (m + 3)*x + 2*m + 2
assert expand(discriminant(p, x) - (m - 1)**2) == 0
assert set(solve((m - 1)**2 - 9, m)) == {4, -2}
for mv in [R(k, 2) for k in range(-20, 21)]:
    r = solve(p.subs(m, mv), x)
    r = r if len(r) == 2 else r * 2
    assert simplify(r[0]*r[1] - 2*(r[0] + r[1]) + 4) == 0
    assert (abs(r[0] - r[1]) == 3) == (mv in (4, -2)), mv
assert roots(p.subs(m, 4)) == {2, 5} and roots(p.subs(m, -2)) == {2, -1}
# 019
f = (x - 1)*(x + 1)*(x + 3)*(x + 5) - 105
assert expand((x - 1)*(x + 5)) == x**2 + 4*x - 5 and expand((x + 1)*(x + 3)) == x**2 + 4*x + 3
assert set(solve((T - 5)*(T + 3) - 105, T)) == {12, -10}
assert discriminant(x**2 + 4*x + 10, x) < 0 and roots(x**2 + 4*x - 12) == {2, -6}
assert roots(f) == {2, -6}
# 020
p = x**2 - 2*m*x + m**2 - m + 2
assert expand(discriminant(p, x)/4) == m - 2
assert expand((2*m)**2 - 2*(m**2 - m + 2)) == 2*m**2 + 2*m - 4
assert set(solve(2*m**2 + 2*m - 4 - 36, m)) == {4, -5}
good = []
for mv in [R(k, 4) for k in range(-40, 41)]:
    r = solve(p.subs(m, mv), x)
    r = r if len(r) == 2 else r * 2
    if len(r) == 2 and all(v.is_real and v > 0 for v in r) and simplify(r[0]**2 + r[1]**2 - 36) == 0:
        good.append(mv)
assert good == [4], good
r = solve(p.subs(m, 4), x)
assert simplify(r[0]*r[1]/2) == 7
assert expand((m - R(1, 2))**2 + R(7, 4)) == m**2 - m + 2
# ---- 021..031
from sympy import cancel, factor
y_ = symbols("y_", real=True)

# 021
assert roots(3*x**2 - 5*x) == {0, R(5, 3)} and roots(3*x - 5) == {R(5, 3)}  # dividing by x loses 0
assert roots(2*x**2 - 50) == {5, -5}

# 022
assert discriminant(x**2 - 2*sqrt(3)*x - 6, x) / 4 == 9
assert roots(x**2 - 2*sqrt(3)*x - 6) == {sqrt(3) + 3, sqrt(3) - 3}
assert -3*2026 == -6078 and discriminant(-3*x**2 + 5*x + 2026, x) == 25 + 24312 > 0

# 023
for p23, sign in [(3*x**2 - 11*x + 5, "pos"), (2*x**2 + 9*x + 4, "neg"), (5*x**2 + 3*x - 7, "mixed")]:
    r = list(roots(p23))
    assert len(r) == 2 and discriminant(p23, x) > 0
    s = sorted(float(t) for t in r)
    assert {"pos": s[0] > 0, "neg": s[1] < 0, "mixed": s[0] < 0 < s[1]}[sign]
assert discriminant(3*x**2 - 11*x + 5, x) == 61 and discriminant(2*x**2 + 9*x + 4, x) == 49

# 024
r1, r2 = sorted(roots(x**2 - 3*x + 1), key=float)
assert discriminant(x**2 - 3*x + 1, x) == 5 and r1 > 0 and r2 > 0
assert expand(r1**3 + 8*r2) == 21 and expand(r2**3 + 8*r1) == 21
assert expand(x**3 - (8*x - 3) - (x + 3)*(x**2 - 3*x + 1)) == 0  # x^3 = 8x - 3 modulo the equation
B24, C24 = sqrt(r1) + sqrt(r2), r1*sqrt(r1) + r2*sqrt(r2)
assert abs((B24 - sqrt(5)).evalf(50)) < 1e-40 and abs((C24 - 2*sqrt(5)).evalf(50)) < 1e-40
assert expand(r1*r2) == 1 and expand(r1 + r2) == 3
assert expand(((sqrt(5) - 1)/2)**2) == r1 and expand(((sqrt(5) + 1)/2)**2) == r2  # sqrt of roots, exact
assert expand(((sqrt(5) - 1)/2)**3 + ((sqrt(5) + 1)/2)**3) == 2*sqrt(5)

# 025
assert roots(3*x**2 - 8*x + 5) == {1, R(5, 3)} and roots(2*x**2 + 3*x - 5) == {1, R(-5, 2)}
assert factor(3*x**2 - 8*x + 5) == (x - 1)*(3*x - 5) and factor(2*x**2 + 3*x - 5) == (x - 1)*(2*x + 5)
assert cancel((3*x**2 - 8*x + 5) / (2*x**2 + 3*x - 5)) == (3*x - 5) / (2*x + 5)

# 026
pa = (2 - sqrt(3))*x**2 + 2*sqrt(3)*x - (2 + sqrt(3))
assert expand(pa.subs(x, 1)) == 0 and expand(pa.subs(x, -7 - 4*sqrt(3))) == 0
pb = (sqrt(3) + 1)*x**2 + 2*sqrt(3)*x + sqrt(3) - 1
assert expand(pb.subs(x, -1)) == 0 and expand(pb.subs(x, sqrt(3) - 2)) == 0
assert simplify(-(2 + sqrt(3)) / (2 - sqrt(3)) - (-7 - 4*sqrt(3))) == 0
assert simplify(-(sqrt(3) - 1) / (sqrt(3) + 1) - (sqrt(3) - 2)) == 0

# 027
a_, b_, c_ = symbols("a_ b_ c_", real=True)
p27 = (a_ - b_)*x**2 + (b_ - c_)*x + c_ - a_
assert expand(p27.subs(x, 1)) == 0
assert simplify(p27.subs(x, (c_ - a_) / (a_ - b_))) == 0
assert expand(discriminant(p27, x) - (2*a_ - b_ - c_)**2) == 0
assert solve((c_ - a_) / (a_ - b_) - 1, a_) == [(b_ + c_) / 2]
dd = symbols("dd", positive=True)
for sg in (1, -1):  # p - q = sg*dd, |p - q| = dd: +-|p-q| and +-(p-q) give same roots
    q27 = a_ - b_ - sg*dd
    assert {simplify((a_ - b_ + q27 + e*dd) / (2*(a_ - b_))) for e in (1, -1)} == {1, simplify(q27 / (a_ - b_))}

# 028
assert expand((x - 2 - sqrt(3))*(x - 2 + sqrt(3))) == x**2 - 4*x + 1
assert roots(x**2 - 4*x + 1) == {2 + sqrt(3), 2 - sqrt(3)}
assert roots(6*x**2 + 13*x - 5) == {R(1, 3), R(-5, 2)} and expand((3*x - 1)*(2*x + 5)) == 6*x**2 + 13*x - 5

# 029
sol29 = solve([x**2 + y_**2 + x + y_ - 18, x*y_ - 6], [x, y_])
exp29 = {(2, 3), (3, 2), (-3 + sqrt(3), -3 - sqrt(3)), (-3 - sqrt(3), -3 + sqrt(3))}
assert {(simplify(p), simplify(q)) for p, q in sol29} == exp29
assert set(solve(X**2 + X - 30, X)) == {5, -6}

# 030
assert set(solve(5*(x - 10)**2 - 1125, x)) == {25, -5}
assert expand(5*(x - 10)**2 - 1125) == 5*(x**2 - 20*x - 125)
assert (25 - 10)**2 * 5 == 1125

# 031
assert 4 + R(48, 60) == R(24, 5)
assert set(solve(1/x + 1/(x + 4) - R(5, 24), x)) == {8, R(-12, 5)}
assert expand(24*(x + 4) + 24*x - 5*x*(x + 4)) == -(5*x**2 - 28*x - 96)
assert R(1, 8) + R(1, 12) == R(5, 24) and 8 > R(24, 5)
print("PT2: all 31 problems verified")
