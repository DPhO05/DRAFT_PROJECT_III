from sympy import Abs, Eq, Rational as R, S, solve, solveset, symbols, simplify, Poly

x, y, m, a, b = symbols("x y m a b")

# 001
f = lambda t: 3 * t - 2
assert (f(0), f(2), f(R(-1, 3))) == (-2, 4, -3)

# 002 a) (1),(3) bac nhat; (2),(4) khong
for expr, isfirst, ab in [(5 - 2 * x, True, (-2, 5)), (2 * x**2 + 1, False, None),
                          (x / 3, True, (R(1, 3), 0)), (2 * (x - 1) - 2 * x + 3, False, None)]:
    p = Poly(expr, x)
    ok = p.degree() == 1
    assert ok == isfirst
    if ok:
        assert (p.coeff_monomial(x), p.coeff_monomial(1)) == ab
assert (2 * (x - 1) - 2 * x + 3).expand() == 1
# 002 b) a = 2m-4 != 0 <=> m != 2
assert solve(2 * m - 4, m) == [2]

# 003
d = lambda t: -2 * t + 3
assert d(1) == 1 and d(2) != 1
A = (0, d(0)); B = (solve(Eq(d(x), 0), x)[0], 0)
assert A == (0, 3) and B == (R(3, 2), 0)
assert R(1, 2) * Abs(A[1]) * Abs(B[0]) == R(9, 4)

# 004: d1 slope m+1, int 3; d2 slope 2, int m; m != -1
assert solve(Eq(m + 1, 2), m) == [1] and 1 != 3            # a) m=1, b'=1 != 3
cut = [t for t in range(-10, 11) if t != -1 and t + 1 != 2]  # b) m != 1, m != -1
assert 1 not in cut and -1 not in cut and len(cut) == 19
assert solve([Eq(m + 1, 2), Eq(3, m)], m) == []             # c) no m

# 005: a = -3, through (2;0)
bb = solve(Eq(0, -3 * 2 + b), b)[0]
assert bb == 6 and bb != 5

# 006
yA = lambda t: 12 * t + 15; yB = lambda t: 14 * t + 9
xs = solve(Eq(yA(x), yB(x)), x)
assert xs == [3] and yA(3) == 51
assert (yA(10), yB(10), yB(10) - yA(10)) == (135, 149, 14)

# 007
xi = solve(Eq(2 * x + m - 1, -x + 2 * m + 2), x)[0]
assert simplify(xi - (m + 3) / 3) == 0
assert solve(Eq(xi, 0), m) == [-3]
yi = (2 * xi + m - 1).simplify()
assert simplify(yi - (5 * m + 3) / 3) == 0
mm = solve(Eq(yi, 0), m)
assert mm == [R(-3, 5)] and xi.subs(m, mm[0]) == R(4, 5) and yi.subs(m, mm[0]) == 0

# 008
I = solve([Eq(y, 2 * x - 1), Eq(y, -x + 5)], [x, y])
assert I == {x: 2, y: 3}
m8 = solve(Eq(3, (m - 1) * 2 + m), m)
assert m8 == [R(5, 3)] and R(5, 3) - 1 not in (2, -1)

# 009: fixed point of y = (m-1)x + 2m - 3 for all m
sol = solve(Poly((m - 1) * x + 2 * m - 3 - y, m).coeffs(), [x, y])
assert sol == {x: -2, y: -1}
assert simplify((m - 1) * (-2) + 2 * m - 3) == -1
assert solve([Eq(y, -x - 3), Eq(y, x + 1)], [x, y]) == {x: -2, y: -1}  # cach 2: d_0, d_2

# 010
assert solve([Eq(m - 3, -2)], m) == {m: 1} and (1 - 1) != 5
Ay = m - 1; Bx = solve(Eq((m - 3) * x + m - 1, 0), x)[0]
assert simplify(Bx - (1 - m) / (m - 3)) == 0
ms = solveset(Eq(Abs(m - 1), Abs(Bx)), m, domain=S.Reals) - {1, 3}
assert ms == {2, 4}, ms
for mv in (2, 4):
    assert Abs(Ay.subs(m, mv)) == Abs(Bx.subs(m, mv)) != 0

# ---------------- 011..020
from sympy import sqrt, Function, expand, maximum, Interval, oo, divisors

# 011: slopes and angle type
for expr, slope in [(4*x - 7, 4), (3 - R(2, 5)*x, R(-2, 5)), ((x + 6)/2, R(1, 2)), (-(x + 1), -1)]:
    assert Poly(expand(expr), x).coeff_monomial(x) == slope
assert [s > 0 for s in (4, R(-2, 5), R(1, 2), -1)] == [True, False, True, False]

# 012
m12 = solve(Eq(4, (2*m - 1)*(-1) + m + 2), m)
assert m12 == [-1] and 2*m12[0] - 1 != 0
f12 = ((2*m - 1)*x + m + 2).subs(m, -1)
assert expand(f12) == -3*x + 1
x0 = solve(Eq(2*x, f12), x)
assert x0 == [R(1, 5)] and 2*x0[0] == R(2, 5)

# 013
s13 = solve([Eq(b, -2), Eq(4, 3*a + b)], [a, b])
assert s13 == {a: 2, b: -2}
assert solve(2*x - 2, x) == [1]

# 014
s14 = solve([Eq(3, a + b), Eq(-3, -2*a + b)], [a, b])
assert s14 == {a: 2, b: 1}
assert 2*3 + 1 == 7
k = symbols("k")
k14 = solve(Eq(k - 3, 2*(2*k) + 1), k)
assert k14 == [R(-4, 3)] and 2*(2*k14[0]) + 1 == k14[0] - 3 == R(-13, 3)

# 015
s15 = solve([Eq(1800, 2*a + b), Eq(3600, 5*a + b)], [a, b])
assert s15 == {a: 600, b: 600}
assert R(3600 - 1800, 3) == 600 and 1800 - 2*600 == 600       # cach 2
assert solve(Eq(600*x + 600, 6000), x) == [9] and 5400 / 600 == 9

# 016
C = solve([Eq(y, x + 2), Eq(y, -2*x + 8)], [x, y])
assert C == {x: 2, y: 4}
A16, B16 = solve(x + 2, x)[0], solve(-2*x + 8, x)[0]
assert (A16, B16) == (-2, 4)
assert R(1, 2) * (B16 - A16) * C[y] == 12

# 017: integer m, m != 1, m != 4, integer intersection
good = []
for mv in range(-50, 51):
    if mv in (1, 4):
        continue
    xs = solve(Eq((mv - 1)*x + 2, 3*x - 1), x)
    assert len(xs) == 1
    xv = xs[0]; yv = 3*xv - 1
    if xv.is_integer and yv.is_integer:
        good.append(mv)
assert good == [3, 5, 7], good
assert {4 + d for d in (-3, -1, 1, 3)} == {1, 3, 5, 7}

# 018: f(f(x)) = 4x + 3
s18 = solve(Poly(expand(a*(a*x + b) + b - (4*x + 3)), x).coeffs(), [a, b], dict=True)
assert {(d[a], d[b]) for d in s18} == {(2, 1), (-2, -3)}
for av, bv in [(2, 1), (-2, -3)]:
    g = lambda t: av*t + bv
    assert expand(g(g(x))) == 4*x + 3

# 019
AB = solve([Eq(1, b), Eq(3, a + b)], [a, b]); BC = solve([Eq(3, a + b), Eq(2, 4*a + b)], [a, b])
assert AB == {a: 2, b: 1} and BC == {a: R(-1, 3), b: R(10, 3)}
assert 2*4 + 1 != 2                                            # A, B, C not collinear
D = solve([Eq(y, 2*x - 6), Eq(y, -R(1, 3)*x + 1)], [x, y])
assert D == {x: 3, y: 0}
assert (0 + 4 - 1, 1 + 2 - 3) == (3, 0)                        # D = A + C - B

# 020: OH^2 = (m+2)^2/(m^2+1), max 5 at m = 1/2
mr = symbols("mr", real=True)
OA2 = (mr + 2)**2; OB2 = (mr + 2)**2 / mr**2
OH2 = simplify(OA2*OB2 / (OA2 + OB2))
assert simplify(OH2 - (mr + 2)**2/(mr**2 + 1)) == 0
assert simplify(5 - OH2 - (2*mr - 1)**2/(mr**2 + 1)) == 0
assert maximum((mr + 2)**2/(mr**2 + 1), mr, S.Reals) == 5
assert OH2.subs(mr, R(1, 2)) == 5 and sqrt(5)**2 == 5
# independent: foot of perpendicular H from O to y = mx + m + 2, check |OH|^2
for mv in (R(1, 2), R(3), R(-1), R(5, 7)):
    hx = symbols("hx")
    H = solve(Eq(hx + mv*(mv*hx + mv + 2), 0), hx)[0]          # OH . direction(1, m) = 0
    assert simplify(H**2 + (mv*H + mv + 2)**2 - OH2.subs(mr, mv)) == 0

# 021: d1 y=-x/2 through O, A(2;-1); d2 y=-x/2+2 through B(0;2), C(4;0); parallel
f1 = lambda t: -R(1, 2)*t; f2 = lambda t: -R(1, 2)*t + 2
assert f1(0) == 0 and f1(2) == -1 and f2(0) == 2 and solve(f2(x), x) == [4]
assert -R(1, 2) == -R(1, 2) and 0 != 2

# 022: F = 9/5 C + 32
F = lambda c: R(9, 5)*c + 32
assert (F(25), F(-10)) == (77, 14) and solve(Eq(x, F(x)), x) == [-40]

# 023: y = -6x + 45
g = lambda t: -6*t + 45
assert g(0) == 45 and solve(g(x), x) == [R(15, 2)] and R(15, 2)*60 == 7*60 + 30

# 024: y = (m-2)x + 2m - 1
assert solve(Eq(2*m - 1, 5), m) == [3]
assert solve(Eq(0, (m - 2)*(-3) + 2*m - 1), m) == [5] and solve(3*x + 9, x) == [-3]

# 025: y = (m-1)x + 3, area = 9/(2|m-1|) = 3
mr2 = symbols("mr2", real=True)
s25 = solve(Eq(R(9, 2)/Abs(mr2 - 1), 3), mr2)
assert set(s25) == {R(5, 2), -R(1, 2)}
for mv in s25:
    xi = solve((mv - 1)*x + 3, x)[0]
    assert R(1, 2)*3*Abs(xi) == 3

# 026: M on y = 2x - 6 with |y| = |x|
xr = symbols("xr", real=True)
s26 = solve(Eq(Abs(2*xr - 6), Abs(xr)), xr)
assert {(v, 2*v - 6) for v in s26} == {(6, 6), (2, -2)}

# 027
assert expand(3*x - (x - 3)) == 2*x + 3
assert solve(4*x - 2*y - 2, y) == [2*x - 1] and solve(x + 2*y + 2, y) == [-x/2 - 1]
s27 = [v for v in solve(Eq(m**2 - 2, 2), m) if v + 1 != -1 and v**2 != 2]
assert s27 == [2] and (2**2 - 2, 2 + 1) == (2, 3)

# 028: M(m-1; 2m+3) on y = 2x + 5; never on y = 2x + 1; on y = -x + 2 iff m = 0
assert expand(2*(m - 1) + 5 - (2*m + 3)) == 0
assert solve(Eq(2*m + 3, 2*(m - 1) + 1), m) == []
assert solve(Eq(2*m + 3, -(m - 1) + 2), m) == [0] and (0 - 1, 0 + 3) == (-1, 3)

from sympy import Interval, minimum, oo

# 029: through A(4;1), OP = 2 OQ  =>  |a| = 1/2
s29 = solve([Eq(1, 4*a + b), Eq(a**2, R(1, 4))], [a, b], dict=True)
assert {(d[a], d[b]) for d in s29} == {(R(1, 2), -1), (-R(1, 2), 3)}
for d in s29:
    P = solve(d[a]*x + d[b], x)[0]
    assert d[b] != 0 and Abs(P) == 2*Abs(d[b])

# 030: A(2;4), B(4;2), O; area 6 (shoelace + both methods)
A30 = solve([Eq(y, 2*x), Eq(y, -x + 6)], [x, y]); B30 = solve([Eq(y, x/2), Eq(y, -x + 6)], [x, y])
assert A30 == {x: 2, y: 4} and B30 == {x: 4, y: 2} and solve([Eq(y, 2*x), Eq(y, x/2)], [x, y]) == {x: 0, y: 0}
assert Abs(2*2 - 4*4)/2 == 6
# a) steps (both methods): 3x = 6; x = -2x + 12, 3x = 12; 2 != 1/2, 3/2 x = 0
assert solve(3*x - 6, x) == [2] and solve(x - (-2*x + 12), x) == solve(3*x - 12, x) == [4]
assert 2 != R(1, 2) and solve(R(3, 2)*x, x) == [0] and 2*2 == 4 and R(1, 2)*4 == 2
assert R(1, 2)*6*4 - R(1, 2)*6*2 == 6 and 16 - (4 + 2 + 4) == 6

# 031: through M(1;2), a < 0, S(t) = (2+t)^2/(2t), t = -a > 0; min 4 at t = 2
tp = symbols("tp", positive=True)
S31 = R(1, 2)*((2 + tp)/tp)*(2 + tp)
assert simplify(S31 - 4 - (tp - 2)**2/(2*tp)) == 0
assert minimum(S31, tp, S.Reals.intersect(Interval.open(0, oo))) == 4 and S31.subs(tp, 2) == 4
assert (-2*1 + 4, solve(-2*x + 4, x)) == (2, [2])

print("verify_8-ham-so-bac-nhat: all 31 OK")
