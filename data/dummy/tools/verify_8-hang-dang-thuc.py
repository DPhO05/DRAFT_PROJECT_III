"""Re-derive every boxed answer of 8-hang-dang-thuc.tex."""
from sympy import Eq, Rational, expand, simplify, solve, symbols, sqrt, Poly

x, y, a, b, c = symbols("x y a b c")

# 001
assert expand((x + 3) ** 2) == x**2 + 6 * x + 9
assert expand((2 * x - y) ** 2) == 4 * x**2 - 4 * x * y + y**2
assert expand((x - 4) * (x + 4)) == x**2 - 16
# 002
assert expand((2 * x - 1) ** 3) == 8 * x**3 - 12 * x**2 + 6 * x - 1
assert expand((x + 2) ** 3) == x**3 + 6 * x**2 + 12 * x + 8
# 003
assert 99**2 == 9801 and 101 * 99 == 9999 and 36**2 + 2 * 36 * 14 + 14**2 == 2500
# 004
P = (x + 2) * (x**2 - 2 * x + 4) - (x - 1) ** 3 - 3 * x**2
assert expand(P) == 9 - 3 * x
assert P.subs(x, Rational(-2, 3)) == 11
# 005
B = (2 * x + 5) ** 2 + (2 * x - 1) ** 2 - 2 * (2 * x + 5) * (2 * x - 1)
assert expand(B) == 36
assert expand(2 * (2 * x + 5) * (2 * x - 1)) == 8 * x**2 + 16 * x - 10
# 006
sol = solve(Eq((x + 3) ** 2 - x**2, 81), x)
assert sol == [12]
# 007: x, y roots of t^2 - 3t - 10
t = symbols("t")
r = solve(t**2 - 3 * t - 10, t)
X, Y = max(r), min(r)
assert X + Y == 3 and X * Y == -10
assert X**2 + Y**2 == 29 and X**3 + Y**3 == 117 and X - Y == 7
# 008
Q = x**2 - 2 * x * y + 2 * y**2 + 4 * y + 7
assert expand((x - y) ** 2 + (y + 2) ** 2 + 3 - Q) == 0
assert Q.subs({x: -2, y: -2}) == 3
# 009
assert expand((a**3 + b**3 + c**3 - 3 * a * b * c).subs(c, -a - b)) == 0
# 010: general identity with a+b+c=0, plus a concrete triple
cc = -a - b
S2 = expand(a**2 + b**2 + cc**2)
S4 = expand(a**4 + b**4 + cc**4)
assert expand(S4 - S2**2 / 2) == 0  # a^4+b^4+c^4 = (a^2+b^2+c^2)^2/2
assert Rational(14**2, 2) == 98
assert expand((a * b + b * cc + cc * a) - (0 - S2) / 2) == 0  # ab+bc+ca = -S2/2 -> -7
trip = (1, 2, -3)
assert sum(trip) == 0 and sum(v**2 for v in trip) == 14 and sum(v**4 for v in trip) == 98
# 011
assert expand((x + 5) ** 2) == x**2 + 10 * x + 25
assert expand((2 * x - 3) * (2 * x + 3)) == 4 * x**2 - 9
assert expand((x + 1) * (x**2 - x + 1)) == x**3 + 1
# 012
M = x**3 + 3 * x**2 + 3 * x + 1
N = x**3 - 6 * x**2 + 12 * x - 8
assert expand((x + 1) ** 3 - M) == 0 and expand((x - 2) ** 3 - N) == 0
assert M.subs(x, 99) == 1_000_000 and N.subs(x, 22) == 8000
# 013
assert expand((a + 4) * (a - 4) - a**2) == -16
assert 58 * 50 == 2900 == 54**2 - 16
# 014
assert solve(Eq((x + 3) ** 2 - (x - 2) * (x + 2), 31), x) == [3]
assert expand((x + 3) ** 2 - (x - 2) * (x + 2)) == 6 * x + 13
assert solve(Eq((x - 1) ** 3 - x * (x**2 - 3 * x), 14), x) == [5]
assert expand((x - 1) ** 3 - x * (x**2 - 3 * x)) == 3 * x - 1
# 015
assert expand((x - 3) ** 2 + 1 - (x**2 - 6 * x + 10)) == 0
D = 4 * x - x**2 + 3
assert expand(7 - (x - 2) ** 2 - D) == 0 and D.subs(x, 2) == 7
# 016
E = x**2 + y**2 - 4 * x + 6 * y + 13
assert expand((x - 2) ** 2 + (y + 3) ** 2 - E) == 0 and E.subs({x: 2, y: -3}) == 0
# 017
n = symbols("n")
assert expand((n + 1) ** 3 - n**3) == 3 * n**2 + 3 * n + 1
assert [k for k in range(1, 1000) if (k + 1) ** 3 - k**3 == 217] == [8]
assert 11**3 - 10**3 == 331
# 018
A = (5 + 1) * (5**2 + 1) * (5**4 + 1) * (5**8 + 1)
assert 4 * A == 5**16 - 1 and A < 5**16
# 019
L = (a + b + c) ** 3 - a**3 - b**3 - c**3
assert expand(L - 3 * (a + b) * (b + c) * (c + a)) == 0
bracket = (a + b + c) ** 2 + a * (a + b + c) + a**2 - b**2 + b * c - c**2
assert expand(bracket - (3 * a**2 + 3 * a * b + 3 * a * c + 3 * b * c)) == 0
assert expand(bracket - 3 * (a + b) * (a + c)) == 0
assert expand(L - 3 * (a + b) * (a * b + a * c + b * c + c**2)) == 0
# 020
sq = [k for k in range(0, 100_000) if int(sqrt(k * k + 4 * k + 97)) ** 2 == k * k + 4 * k + 97]
assert sq == [12, 44], sq
assert 12**2 + 48 + 97 == 17**2 and 44**2 + 176 + 97 == 47**2
# 021
assert expand((x + 3) * (x**2 - 3 * x + 9)) == x**3 + 27
assert expand((2 - y) * (4 + 2 * y + y**2)) == 8 - y**3
assert expand((x - 2) * (x**2 + 2 * x + 4)) == x**3 - 8
# 022
assert expand((a + b + c) ** 2 - (a**2 + b**2 + c**2 + 2 * a * b + 2 * b * c + 2 * c * a)) == 0
assert expand((x - 2 * y + 3) ** 2) == expand(x**2 + 4 * y**2 - 4 * x * y + 6 * x - 12 * y + 9)
# 023
assert sorted(solve((2 * x - 1) ** 2 - (x + 3) ** 2, x)) == [Rational(-2, 3), 4]
assert expand((x - 4) * (3 * x + 2) - ((2 * x - 1) ** 2 - (x + 3) ** 2)) == 0
# 024
k = symbols("k", integer=True)
assert expand((2 * k + 3) ** 2 - (2 * k + 1) ** 2) == 8 * k + 8
assert all(((2 * j + 3) ** 2 - (2 * j + 1) ** 2) % 8 == 0 for j in range(-100, 100))
assert [(2 * j + 1, 2 * j + 3) for j in range(0, 1000) if (2 * j + 3) ** 2 - (2 * j + 1) ** 2 == 136] == [(33, 35)]
# 025
assert [(X, Y) for X in range(1, 200) for Y in range(1, 200) if X**3 - Y**3 == 19] == [(3, 2)]
assert expand((y + 1) ** 2 + (y + 1) * y + y**2) == 3 * y**2 + 3 * y + 1
assert expand((y + 3) * (y - 2)) == y**2 + y - 6
# 026
assert 29**2 - 29 * 43 + 43**2 == 1443 and 29**3 + 43**3 == 72 * 1443
assert expand((n + 5) ** 3 - (n - 1) ** 3 - 6 * ((n + 5) ** 2 + (n + 5) * (n - 1) + (n - 1) ** 2)) == 0
assert all(((j + 5) ** 3 - (j - 1) ** 3) % 6 == 0 for j in range(-100, 100))
# 027
P = (x - 1) * (x + 1) * (x**2 + x + 1) * (x**2 - x + 1)
assert expand(P) == x**6 - 1
assert sorted(s for s in solve(P - 63, x) if s.is_real) == [-2, 2]
# 028
r28 = solve([a + b - 10, a**3 + b**3 - 370], [a, b], dict=True)
r28 = [s for s in r28 if s[a].is_real and s[a] > s[b] > 0]
assert r28 == [{a: 7, b: 3}], r28
assert 7**2 + 3**2 == 58 and 7 * 3 == 21
# 029
assert 2025**2 - 2024 * 2026 == 1
assert Rational(63**2 - 47**2, 215**2 - 105**2) == Rational(1, 20)
# 030: x > 0, x^2 + 1/x^2 = 7
r30 = [r for r in solve(x**2 + x**-2 - 7, x) if r.is_real and r > 0]
assert len(r30) == 2
for r in r30:
    assert simplify(r + 1 / r - 3) == 0
    assert simplify(r**3 + r**-3 - 18) == 0
    assert simplify(r**5 + r**-5 - 123) == 0
# 031
F = a**3 + b**3 + c**3 - 3 * a * b * c
assert expand(F - (a + b + c) * (a**2 + b**2 + c**2 - a * b - b * c - c * a)) == 0
assert expand(2 * F - (a + b + c) * ((a - b) ** 2 + (b - c) ** 2 + (c - a) ** 2)) == 0
assert all(p**3 + q**3 + s**3 >= 3 * p * q * s for p in range(6) for q in range(6) for s in range(6))
print("HDT: all 31 answers verified")
