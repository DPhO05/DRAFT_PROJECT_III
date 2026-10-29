from sympy import Eq, Rational as R, linsolve, solve, symbols, simplify, Matrix, expand, sqrt, Symbol, reduce_inequalities, Interval, oo, diff, limit

x, y, m, u, v = symbols("x y m u v")

def one(eqs):
    s = solve(eqs, [x, y], dict=True)
    assert len(s) == 1, s
    return (s[0][x], s[0][y])

assert one([Eq(x + y, 5), Eq(2 * x - y, 1)]) == (2, 3)                       # 001
assert one([Eq(x - 2 * y, 1), Eq(3 * x + y, 10)]) == (3, 1)                  # 002
assert linsolve([2 * x - 3 * y - 4, -4 * x + 6 * y - 1], [x, y]).is_empty    # 003 vo nghiem
# 004
assert one([Eq(2 * x + y, 2), Eq(x + y, 1)]) == (1, 0)
assert Matrix([[m, 1], [1, 1]]).det() == m - 1
s4 = solve([Eq(m * x + y, 2), Eq(x + y, 1)], [x, y], dict=True)[0]
assert simplify(s4[x] - 1 / (m - 1)) == 0 and simplify(s4[y] - (m - 2) / (m - 1)) == 0
assert linsolve([x + y - 2, x + y - 1], [x, y]).is_empty                     # m = 1
assert one([Eq(3 * x + 2 * y, 54000), Eq(2 * x + 5 * y, 69000)]) == (12000, 9000)  # 005
# 006
uv = solve([Eq(u + v, R(5, 6)), Eq(u - v, R(1, 6))], [u, v])
assert uv == {u: R(1, 2), v: R(1, 3)} and (1 / uv[u], 1 / uv[v]) == (2, 3)
assert one([Eq(1 / x + 1 / y, R(5, 6)), Eq(1 / x - 1 / y, R(1, 6))]) == (2, 3)
# 007
L, W = one([Eq(2 * (x + y), 28), Eq(x - y, 4)])
assert (L, W, L * W) == (9, 5, 45) and L > W > 0
# 008
a, b = symbols("a b")
assert solve([Eq(3, a + b), Eq(-1, -a + b)], [a, b]) == {a: 2, b: 1}
# 009
uv = solve([Eq(u + v, R(1, 12)), Eq(8 * u + 15 * v, 1)], [u, v])
assert uv == {u: R(1, 28), v: R(1, 21)}
X, Y = 1 / uv[u], 1 / uv[v]
assert (X, Y) == (28, 21) and X > 12 and Y > 12
assert 8 * (R(1, X) + R(1, Y)) + R(7, 2) * 2 / Y == 1                        # direct story check
# 010
A = Matrix([[m, 1], [1, m]])
assert solve(A.det(), m) == [-1, 1]
s10 = solve([Eq(m * x + y, 2 * m), Eq(x + m * y, m + 1)], [x, y], dict=True)[0]
assert simplify(s10[x] - (2 * m + 1) / (m + 1)) == 0 and simplify(s10[y] - m / (m + 1)) == 0
assert linsolve([x + y - 2, x + y - 2], [x, y]) != set() and len(linsolve([x + y - 2, x + y - 2], [x, y]).free_symbols) == 1  # m=1 infinite
assert linsolve([-x + y + 2, x - y], [x, y]).is_empty                        # m=-1 none
good = []
for mv in range(-1000, 1001):
    if mv in (1, -1):
        continue
    sx, sy = s10[x].subs(m, mv), s10[y].subs(m, mv)
    if sx.is_integer and sy.is_integer:
        good.append((mv, sx, sy))
assert good == [(-2, 3, 2), (0, 1, 0)], good

# 011: only (2;-1) satisfies both; (-1;1) only eq1, (4;1) only eq2
e1 = lambda X, Y: 2 * X + 3 * Y == 1
e2 = lambda X, Y: X - Y == 3
assert [(p, e1(*p), e2(*p)) for p in [(-1, 1), (2, -1), (4, 1)]] == [((-1, 1), True, False), ((2, -1), True, True), ((4, 1), False, True)]
assert one([Eq(2 * x + 3 * y, 1), Eq(x - y, 3)]) == (2, -1)
# 012: infinitely many, x = 2y + 3
s12 = linsolve([3 * x - 6 * y - 9, -x + 2 * y + 3], [x, y])
(gx, gy), = s12
assert gy == y and simplify(gx - (2 * y + 3)) == 0
assert expand(3 * (2 * y + 3) - 6 * y) == 9 and 3 * 3 - 6 * 0 == 9 and -3 + 0 == -3
# 013: both methods
assert one([Eq((x + y) / 3 + (x - y) / 2, 4), Eq((x + y) / 2 - (x - y) / 4, 2)]) == (5, 1)
assert expand(2 * (x + y) + 3 * (x - y)) == 5 * x - y and expand(2 * (x + y) - (x - y)) == x + 3 * y
assert one([Eq(5 * x - y, 24), Eq(x + 3 * y, 8)]) == (5, 1)
assert solve([Eq(2 * u + 3 * v, 24), Eq(2 * u - v, 8)], [u, v]) == {u: 6, v: 4}
# 014: percent
X14, Y14 = one([Eq(x + y, 600), Eq(x * R(115, 100) + y * R(110, 100), 680)])
assert (X14, Y14) == (400, 200) and one([Eq(x + y, 600), Eq(3 * x + 2 * y, 1600)]) == (400, 200)
assert X14 * R(115, 100) == 460 and Y14 * R(110, 100) == 220
# 015: M = d1 ∩ d2, line through M and A(-2,-9)
assert one([Eq(y, 2 * x - 1), Eq(y, -x + 5)]) == (2, 3)
assert solve([Eq(3, 2 * a + b), Eq(-9, -2 * a + b)], [a, b]) == {a: 3, b: -3}
# 016: x>0, y>0  <=>  m > 1/3
s16 = solve([Eq(x + y, 3), Eq(m * x - y, 1)], [x, y], dict=True)[0]
assert simplify(s16[x] - 4 / (m + 1)) == 0 and simplify(s16[y] - (3 * m - 1) / (m + 1)) == 0
assert linsolve([x + y - 3, -x - y - 1], [x, y]).is_empty                    # m = -1
mr = Symbol("mr", real=True)
pos = reduce_inequalities([4 / (mr + 1) > 0, (3 * mr - 1) / (mr + 1) > 0], mr)
assert pos.as_set() == Interval.open(R(1, 3), oo), pos
# 017: sqrt substitution
assert solve([Eq(2 * u + 3 * v, 10), Eq(3 * u - 2 * v, 2)], [u, v]) == {u: 2, v: 2}
assert 2 * (3 - 1) + 3 * sqrt(3 + 1) == 10 and 3 * (3 - 1) - 2 * sqrt(3 + 1) == 2
xr, yr = symbols("xr yr", real=True)
assert solve([2 * (xr - yr) + 3 * sqrt(xr + 1) - 10, 3 * (xr - yr) - 2 * sqrt(xr + 1) - 2], [xr, yr], dict=True) == [{xr: 3, yr: 1}]
# 018: canoe
uv = solve([Eq(60 * u + 48 * v, 6), Eq(40 * u + 80 * v, 7)], [u, v])
assert uv == {u: R(1, 20), v: R(1, 16)}
assert one([Eq(x + y, 20), Eq(x - y, 16)]) == (18, 2)
assert R(60, 20) + R(48, 16) == 6 and R(40, 20) + R(80, 16) == 7
# 019: right triangle legs
assert expand((x + 2) * (y + 2) - x * y - 34) == 2 * x + 2 * y - 30
assert expand((x - 3) * (y - 1) - (x * y - 22)) == -x - 3 * y + 25
L19, W19 = one([Eq(x + y, 15), Eq(x + 3 * y, 25)])
assert (L19, W19) == (10, 5) and R(12 * 7, 2) == R(50, 2) + 17 and R(7 * 4, 2) == R(50, 2) - 11
# 020: always unique, relation, max of x^2+y^2
assert Matrix([[1, m], [m, -1]]).det() == -m**2 - 1
s20 = solve([Eq(x + m * y, 2), Eq(m * x - y, 1)], [x, y], dict=True)[0]
assert simplify(s20[x] - (m + 2) / (m**2 + 1)) == 0 and simplify(s20[y] - (2 * m - 1) / (m**2 + 1)) == 0
assert simplify(s20[x] ** 2 + s20[y] ** 2 - 2 * s20[x] + s20[y]) == 0
assert simplify(s20[x] ** 2 + s20[y] ** 2 - 5 / (m**2 + 1)) == 0
f20 = 5 / (mr**2 + 1)
assert solve(diff(f20, mr), mr) == [0] and f20.subs(mr, 0) == 5 and limit(f20, mr, oo) == 0
assert (s20[x].subs(m, 0), s20[y].subs(m, 0)) == (2, -1)

# 021: An's claim (5000; 8000) satisfies both and system unique; conditions x>0, y>0
assert 5000 > 0 and 8000 > 0 and R(-2, 3) != -3
assert 2 * 5000 + 3 * 8000 == 34000 and 3 * 5000 + 8000 == 23000
assert Matrix([[2, 3], [3, 1]]).det() != 0
assert one([Eq(2 * x + 3 * y, 34000), Eq(3 * x + y, 23000)]) == (5000, 8000)
# 022: symmetric coefficients
assert one([Eq(13 * x + 17 * y, 73), Eq(17 * x + 13 * y, 77)]) == (3, 2)
assert one([Eq(x + y, 5), Eq(x - y, 1)]) == (3, 2)
# 023: a) unique (slopes 2/3 != 4/5); b) none (0x+0y=-1); c) infinite (0x+0y=0)
assert len(linsolve([2 * x - 3 * y - 4, 4 * x - 5 * y - 8], [x, y]).free_symbols) == 0 and R(2, 3) != R(4, 5)
assert expand(sqrt(2) * (x - sqrt(2) * y)) == sqrt(2) * x - 2 * y and sqrt(2) * sqrt(2) - 1 == 1
assert linsolve([sqrt(2) * x - 2 * y - 1, x - sqrt(2) * y - sqrt(2)], [x, y]).is_empty
assert expand(-8 * (R(3, 4) * x - R(1, 2) * y)) == -6 * x + 4 * y and -8 * 2 == -16
s23 = linsolve([R(3, 4) * x - R(1, 2) * y - 2, -6 * x + 4 * y + 16], [x, y])
assert len(s23.free_symbols) == 1
assert all(R(3, 4) * X - R(1, 2) * Y == 2 and -6 * X + 4 * Y == -16 for X, Y in [(0, -4), (2, -1)])
# 024: relation x - 2y + 5 = 0
s24 = solve([Eq(x + y, 3 * m + 1), Eq(x - y, m - 3)], [x, y], dict=True)
assert len(s24) == 1 and s24[0] == {x: 2 * m - 1, y: m + 2}
assert expand(s24[0][x] - 2 * s24[0][y] + 5) == 0
assert expand((x + y) - (3 * (x - y + 3) + 1)) == -2 * x + 4 * y - 10

# 025: sqrt coefficients
r2 = sqrt(2)
s25 = solve([Eq((r2 - 1) * x + y, 3 - r2), Eq(x - (r2 + 1) * y, -1)], [x, y], dict=True)
assert len(s25) == 1 and simplify(s25[0][x] - r2) == 0 and s25[0][y] == 1
assert expand((r2 - 1) * (r2 + 1)) == 1
# 026: (1;2) solution iff m = 3
assert solve(Eq(m**2 + 2, m + 8), m) == [-2, 3] and expand((m - 3) * (m + 2)) == m**2 - m - 6
assert solve(Eq((m + 1) + 2, 6), m) == [3]
assert one([Eq(9 * x + y, 11), Eq(4 * x + y, 6)]) == (1, 2)
# 027: products expand to linear system
assert expand((x + 1) * (y - 2) - (x - 2) * (y + 1)) == -3 * x + 3 * y
assert expand((2 * x - 1) * (y + 1) - 2 * x * (y - 1)) == 4 * x - y - 1
assert one([Eq((x + 1) * (y - 2) - (x - 2) * (y + 1), 6), Eq((2 * x - 1) * (y + 1) - 2 * x * (y - 1), 3)]) == (2, 4)
# 028: |x-1| and 1/(y+1)
assert solve([Eq(3 * u + 4 * v, 11), Eq(u - 6 * v, 0)], [u, v]) == {u: 3, v: R(1, 2)}
for X28 in range(-50, 51):
    for Y28 in range(-50, 51):
        if Y28 == -1:
            continue
        ok = 3 * abs(X28 - 1) + R(4, Y28 + 1) == 11 and abs(X28 - 1) - R(6, Y28 + 1) == 0
        assert ok == ((X28, Y28) in [(4, 1), (-2, 1)])

# 029: line AB, C on it, distinct
assert solve([Eq(1, a + b), Eq(5, 3 * a + b)], [a, b]) == {a: 2, b: -1}
ms = solve(Eq(m**2 - 4, 2 * m - 1), m)
assert ms == [-1, 3] and expand((m + 1) * (m - 3)) == m**2 - 2 * m - 3
good29 = [mv for mv in ms if (mv, mv**2 - 4) not in [(1, 1), (3, 5)]]
assert good29 == [-1]
# 030: unique always; min x^2+y^2 = 7/4 at m = (2 ± sqrt6)/2
assert Matrix([[m - 1, 1], [m, 1]]).det() == -1
s30 = solve([Eq((m - 1) * x + y, 2), Eq(m * x + y, m + 1)], [x, y], dict=True)[0]
assert simplify(s30[x] - (m - 1)) == 0 and simplify(s30[y] - (2 - (m - 1) ** 2)) == 0
t = Symbol("t", nonnegative=True)
assert expand(t + (2 - t) ** 2 - ((t - R(3, 2)) ** 2 + R(7, 4))) == 0
P30 = expand(s30[x] ** 2 + s30[y] ** 2).subs(m, mr)
crit = sorted(solve(diff(P30, mr), mr), key=lambda z: float(z))
vals = [simplify(P30.subs(mr, c)) for c in crit]
assert min(vals) == R(7, 4) and limit(P30, mr, oo) == oo
argmin = [c for c, vv in zip(crit, vals) if vv == R(7, 4)]
assert len(argmin) == 2 and all(simplify(c - w) == 0 for c, w in zip(sorted(argmin, key=float), [(2 - sqrt(6)) / 2, (2 + sqrt(6)) / 2]))
assert simplify(sqrt(R(3, 2)) - sqrt(6) / 2) == 0
# 031: max S = 4 at m=1, min S = -1 at m=-4
assert Matrix([[m, -2], [2, m]]).det() == m**2 + 4
s31 = solve([Eq(m * x - 2 * y, 1), Eq(2 * x + m * y, 7)], [x, y], dict=True)[0]
assert simplify(s31[x] - (m + 14) / (m**2 + 4)) == 0 and simplify(s31[y] - (7 * m - 2) / (m**2 + 4)) == 0
S31 = simplify(s31[x] + s31[y])
assert simplify(S31 - (8 * m + 12) / (m**2 + 4)) == 0
assert simplify(4 - S31 - 4 * (m - 1) ** 2 / (m**2 + 4)) == 0 and simplify(S31 + 1 - (m + 4) ** 2 / (m**2 + 4)) == 0
Sr = S31.subs(m, mr)
assert sorted(solve(diff(Sr, mr), mr)) == [-4, 1] and Sr.subs(mr, 1) == 4 and Sr.subs(mr, -4) == -1 and limit(Sr, mr, oo) == 0
assert (s31[x].subs(m, 1), s31[y].subs(m, 1)) == (3, 1) and (s31[x].subs(m, -4), s31[y].subs(m, -4)) == (R(1, 2), R(-3, 2))

print("verify_9-he-phuong-trinh: all 31 OK")
