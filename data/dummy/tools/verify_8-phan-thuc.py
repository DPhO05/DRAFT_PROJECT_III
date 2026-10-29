"""Re-derive every boxed answer in 8-phan-thuc.tex with sympy."""
from pathlib import Path

import sympy as sp

TEX = (Path(__file__).resolve().parents[1] / "bank" / "8-phan-thuc.tex").read_text()
x, y = sp.symbols("x y")
R = sp.Rational


def boxed(s):
    assert "\\boxed{" + s + "}" in TEX, f"boxed text not in tex: {s}"


def same(a, b):
    assert sp.simplify(a - b) == 0, (a, b)


def bad(*polys):
    """Real x where any given polynomial (denominator or divisor numerator) vanishes."""
    out = set()
    for p in polys:
        out |= set(sp.solve(sp.Eq(p, 0), x))
    return out


# 001
assert bad(x - 2) == {2}
assert bad(x**2 - 9) == {3, -3}
boxed(r"x \neq 2"); boxed(r"x \neq 3 \text{ và } x \neq -3")

# 002
same((3*x**2 - 6*x) / (x**2 - 4*x + 4), 3*x / (x - 2))
assert bad(x**2 - 4*x + 4) == {2}
boxed(r"\dfrac{3x}{x - 2} \text{ với } x \neq 2")

# 003
same(x**2 / (x - y) + y**2 / (y - x), x + y)
boxed(r"x + y \text{ với } x \neq y")

# 004
same((x**2 - 9) / (2*x + 4) * (x + 2) / (x**2 - 3*x), (x + 3) / (2*x))
assert bad(2*x + 4, x**2 - 3*x) == {0, -2, 3}
same(((x**2 - 4*x + 4) / (x + 1)) / ((x - 2) / (x**2 + x)), x*(x - 2))
assert bad(x + 1, x**2 + x, x - 2) == {0, -1, 2}  # x - 2: divisor numerator
boxed(r"\dfrac{x + 3}{2x} \text{ với } x \neq 0,\ x \neq -2,\ x \neq 3")
boxed(r"x(x - 2) \text{ với } x \neq 0,\ x \neq -1,\ x \neq 2")

# 005
same((x + 1) / (2*x - 2) - (x - 1) / (2*x + 2) - 2 / (x**2 - 1), 2 / (x + 1))
assert bad(2*x - 2, 2*x + 2, x**2 - 1) == {1, -1}
boxed(r"\dfrac{2}{x + 1} \text{ với } x \neq 1,\ x \neq -1")

# 006
T = 120 / x + 120 / (x + 10)
same(T, 240*(x + 5) / (x*(x + 10)))
assert T.subs(x, 30) == 7
boxed(r"T = \dfrac{240(x + 5)}{x(x + 10)} \text{ (giờ)}"); boxed(r"7 \text{ giờ}")

# 007
P = (1 / (x + 1) + 2 / (x**2 - 1)) * (x**2 - 2*x + 1) / x
same(P, (x - 1) / x)
excl = bad(x + 1, x**2 - 1, x)
assert excl == {0, 1, -1}
roots = set(sp.solve(x**2 - 4*x + 3, x)) - excl
assert roots == {3} and P.subs(x, 3) == R(2, 3)
boxed(r"P = \dfrac{x - 1}{x} \text{ với } x \neq 0,\ x \neq 1,\ x \neq -1"); boxed(r"P = \dfrac{2}{3}")

# 008
Q = (2*x / (x + 3) + x / (x - 3) - (3*x**2 + 9) / (x**2 - 9)) / (3 / (3 - x))
same(Q, 1)
assert bad(x + 3, x - 3, x**2 - 9, 3 - x, sp.Integer(3)) == {3, -3}
boxed(r"Q = 1")

# 009
M = 1 / (x*(x + 1)) + 1 / ((x + 1)*(x + 2)) + 1 / ((x + 2)*(x + 3))
same(M, 3 / (x*(x + 3)))
same((x + 2)*(x + 3) + x*(x + 3) + x*(x + 1), 3*(x + 1)*(x + 2))
assert bad(x*(x + 1), (x + 1)*(x + 2), (x + 2)*(x + 3)) == {0, -1, -2, -3}
assert TEX.count(r"\boxed{M = \dfrac{3}{x(x + 3)} \text{ với } x \neq 0,\ x \neq -1,\ x \neq -2,\ x \neq -3}") == 2

# 010
inner = x / (x**2 - 4) + 2 / (2 - x) + 1 / (x + 2)
div = x - 2 + (10 - x**2) / (x + 2)
same(div, 6 / (x + 2))
same(inner, -6 / ((x - 2)*(x + 2)))
A = inner / div
same(A, 1 / (2 - x))
assert bad(x**2 - 4, 2 - x, x + 2, sp.Integer(6)) == {2, -2}
assert A.subs(x, R(1, 2)) == R(2, 3) and A.subs(x, R(-1, 2)) == R(2, 5)
ints = {k for k in range(-1000, 1001) if k not in (2, -2) and A.subs(x, k).is_integer}
assert ints == {1, 3}, ints
boxed(r"A = \dfrac{1}{2 - x} \text{ với } x \neq 2,\ x \neq -2")
boxed(r"A = \dfrac{2}{3} \text{ khi } x = \dfrac{1}{2};\ A = \dfrac{2}{5} \text{ khi } x = -\dfrac{1}{2}")
boxed(r"x = 1 \text{ hoặc } x = 3")

# 011
assert bad(x + 5) == {-5}
assert ((x**2 - 4) / (x + 5)).subs(x, -1) == R(-3, 4)
boxed(r"P = -\dfrac{3}{4} \text{ tại } x = -1;\ P \text{ không xác định tại } x = -5")

# 012
assert sp.expand((x - 3)*(x**2 - 9) - (x + 3)*(x**2 - 6*x + 9)) == 0
assert sp.factor((x - 3)*(x**2 - 9)) == sp.factor((x - 3)**2*(x + 3))
Apoly = sp.cancel((2*x - 6)*(x**2 + 3*x) / (x**2 - 9))
assert sp.expand(Apoly - 2*x) == 0
same(2*x / (2*x - 6), (x**2 + 3*x) / (x**2 - 9))
boxed(r"(x - 3)(x^2 - 9) = (x + 3)(x^2 - 6x + 9) \text{ nên hai phân thức bằng nhau}"); boxed(r"A = 2x")

# 013
excl = bad(x**2 - 16)
assert excl == {4, -4}
assert set(sp.solve(x**2 - 4*x, x)) - excl == {0}
boxed(r"x = 0")

# 014
MTC = 2*x*(x - 2)*(x + 2)
for orig, num in [(1 / (x**2 + 2*x), 2*(x - 2)), (3 / (x**2 - 4), 6*x), (x / (2*x - 4), x**2*(x + 2))]:
    same(orig, num / MTC)
    assert sp.cancel(MTC / sp.denom(sp.together(orig))).is_polynomial(x)  # MTC divisible by each denominator
assert bad(x**2 + 2*x, x**2 - 4, 2*x - 4) == {0, 2, -2}
boxed(r"\dfrac{2(x - 2)}{2x(x - 2)(x + 2)},\ \dfrac{6x}{2x(x - 2)(x + 2)},\ \dfrac{x^2(x + 2)}{2x(x - 2)(x + 2)}")

# 015
same((x**2 + x*y - 2*y**2) / (x**3 - y**3), (x + 2*y) / (x**2 + x*y + y**2))
assert sp.factor(x**2 + x*y - 2*y**2) == sp.factor((x - y)*(x + 2*y))
assert sp.factor(x**3 - y**3) == (x - y)*(x**2 + x*y + y**2)
assert sp.expand(x**2 + x*y + y**2 - ((x + y/2)**2 + R(3, 4)*y**2)) == 0  # second factor > 0 unless x = y = 0, so x^3 = y^3 iff x = y
boxed(r"\dfrac{x + 2y}{x^2 + xy + y^2} \text{ với } x \neq y")

# 016
ratio = (360 / (x - 6)) / (360 / x)
same(ratio, x / (x - 6))
assert ratio.subs(x, 30) == R(5, 4) and R(360, 24) / R(360, 30) == R(5, 4)
boxed(r"\dfrac{360}{x} \text{ (giờ) và } \dfrac{360}{x - 6} \text{ (giờ)}"); boxed(r"\dfrac{x}{x - 6}"); boxed(r"\dfrac{5}{4}")

# 017
same((1 / x - 1 / y) / (1 / x**2 - 1 / y**2), x*y / (x + y))
boxed(r"\left(\dfrac{1}{x} - \dfrac{1}{y}\right) : \left(\dfrac{1}{x^2} - \dfrac{1}{y^2}\right) = \dfrac{xy}{x + y}")

# 018: both methods
z, t = sp.symbols("z t")
s18 = sp.solve([3*x - y - 3*z, 2*x + y - 7*z], [x, y])
assert s18 == {x: 2*z, y: 3*z}
M = (x**2 - 2*x*y) / (x**2 + y**2)
assert sp.simplify(M.subs(s18)) == R(-8, 13)
assert sp.expand(7*(3*x - y) - 3*(2*x + y)) == 15*x - 10*y
assert ((t**2 - 2*t) / (t**2 + 1)).subs(t, R(2, 3)) == R(-8, 13)
same(M, ((x / y)**2 - 2*(x / y)) / ((x / y)**2 + 1))
assert TEX.count(r"\boxed{M = -\dfrac{8}{13}}") == 2

# 019
B = (x**2 - 4*x + 10) / (x**2 - 4*x + 7)
assert sp.expand(x**2 - 4*x + 7 - ((x - 2)**2 + 3)) == 0
same(B, 1 + 3 / ((x - 2)**2 + 3))
crit = sp.solve(sp.diff(B, x), x)
assert crit == [2] and B.subs(x, 2) == 2 and sp.limit(B, x, sp.oo) == 1
assert sp.maximum(B, x, sp.S.Reals) == 2
boxed(r"\max B = 2 \text{ khi } x = 2")

# 020
a, b, c = sp.symbols("a b c")
P = 1 / (b**2 + c**2 - a**2) + 1 / (c**2 + a**2 - b**2) + 1 / (a**2 + b**2 - c**2)
Pc = P.subs(c, -a - b)
assert sp.simplify(Pc) == 0
assert sp.expand((b**2 + c**2 - a**2).subs(c, -a - b) - (-2*b*(-a - b))) == 0
assert P.subs({a: 1, b: 1, c: -2}) == 0 and P.subs({a: 3, b: -5, c: 2}) == 0
boxed(r"P = 0")


# 021
X, Y = sp.symbols("X Y", nonzero=True)
assert sp.simplify(4*X**2 / (5*Y**3) * 15*Y / (8*X) - 3*X / (2*Y**2)) == 0
assert sp.simplify((6*X**3 / (7*Y)) / (3*X / (14*Y**2)) - 4*X**2*Y) == 0
boxed(r"\dfrac{3x}{2y^2}"); boxed(r"4x^2y")

# 022
assert sp.factor(x**3 + 8) == (x + 2)*(x**2 - 2*x + 4)
B22 = sp.cancel((x**3 + 8)*(x - 3) / (x**2 - 2*x + 4))
assert sp.expand(B22 - (x**2 - x - 6)) == 0
assert sp.expand((x**3 + 8)*(x - 3) - (x**2 - x - 6)*(x**2 - 2*x + 4)) == 0
assert sp.expand(x**2 - 2*x + 4 - ((x - 1)**2 + 3)) == 0  # > 0, safe to cancel
boxed(r"B = x^2 - x - 6")

# 023
a = sp.symbols("a")
num23, den23 = a*x - a*y + 2*x - 2*y, a*x + a*y + 2*x + 2*y
assert sp.factor(num23) == sp.factor((x - y)*(a + 2)) and sp.factor(den23) == sp.factor((x + y)*(a + 2))
same(num23 / den23, (x - y) / (x + y))
boxed(r"\dfrac{x - y}{x + y} \text{ với } x \neq -y,\ a \neq -2")

# 024
def eqfrac(A, B, C, D):
    return sp.expand(A*D - B*C) == 0
assert eqfrac(x - 2, x + 2, 2 - x, -x - 2)
assert eqfrac(x - 2, x + 2, x**2 - 2*x, x**2 + 2*x)
assert not eqfrac(x - 2, x + 2, x**2 - 4, x**2 + 4)
assert sp.expand((x + 2)*(x**2 - 4) - (x - 2)*(x**2 + 4)) == 4*x**2 - 8*x
assert ((x - 2)*(x**2 + 4)).subs(x, 1) == -5 and ((x + 2)*(x**2 - 4)).subs(x, 1) == -9
boxed(r"\dfrac{2 - x}{-x - 2} = \dfrac{x - 2}{x + 2}"); boxed(r"\dfrac{x^2 - 2x}{x^2 + 2x} = \dfrac{x - 2}{x + 2}")
boxed(r"\dfrac{x^2 - 4}{x^2 + 4} \neq \dfrac{x - 2}{x + 2}")

# 025
P25 = (x**2 - 9) / (x**2 - 3*x)
excl = bad(x**2 - 3*x)
assert excl == {0, 3}
same(P25, (x + 3) / x)
assert sp.solve(sp.Eq((x + 3) / x, 2), x) == [3] and 3 in excl  # only candidate rejected
assert sp.solve(sp.Eq((x + 3) / x, 4), x) == [1] and P25.subs(x, 1) == 4
boxed(r"\text{không có giá trị nào của } x"); boxed(r"x = 1")

# 026
Q26 = sp.cancel(((x**2 - 4) / (x**2 - 1)) / ((x**2 + 2*x) / (x - 1)))
same(Q26, (x - 2) / (x*(x + 1)))
same((x**2 + 2*x) / (x - 1) * Q26, (x**2 - 4) / (x**2 - 1))
assert bad(x - 1, x**2 - 1, x**2 + 2*x) == {0, 1, -1, -2}
boxed(r"Q = \dfrac{x - 2}{x(x + 1)} \text{ với } x \neq 0,\ x \neq 1,\ x \neq -1,\ x \neq -2")

# 027
L27, W27 = (x**2 - 1) / x, x**2 / (x + 1)
S27 = L27 * W27
same(S27, x*(x - 1))
same(S27 / ((x - 1) / 2), 2*x)
assert sp.expand((x**2 - 1)*(x + 1) - x**3) == x**2 - x - 1  # length > width when x > 2
assert all((L27 - W27).subs(x, v) > 0 for v in [R(201, 100), 3, 5, 100])
assert S27.subs(x, 5) == 20 and L27.subs(x, 5) == R(24, 5) and W27.subs(x, 5) == R(25, 6) and 20 / R(2) == 10
n27 = sp.cancel(S27 / ((x - 1) / 2))
assert n27.subs(x, R(11, 5)) == R(22, 5) and all(n27.subs(x, v).is_integer for v in range(3, 20))  # x integer needed
boxed(r"S = x(x - 1)\ (\text{m}^2)"); boxed(r"2x \text{ luống}"); boxed(r"S = 20\ \text{m}^2;\ 10 \text{ luống}")

# 028
m = sp.symbols("m", real=True)
den28 = x**2 + 2*x + m
assert sp.expand(den28 - ((x + 1)**2 + m - 1)) == 0
assert sp.solve_univariate_inequality(sp.discriminant(den28, x) < 0, m, relational=False) == sp.Interval.open(1, sp.oo)  # no real root iff m > 1
for mv in [1, 0, -3, R(1, 2)]:
    assert sp.simplify(den28.subs({m: mv, x: -1 + sp.sqrt(1 - mv)})) == 0
boxed(r"m > 1")

# 029
zz = sp.symbols("z")
n29, d29 = x**2 + y**2 - zz**2 + 2*x*y, x**2 - y**2 + zz**2 + 2*x*zz
assert sp.factor(n29) == sp.factor((x + y - zz)*(x + y + zz)) and sp.factor(d29) == sp.factor((x - y + zz)*(x + y + zz))
same(n29 / d29, (x + y - zz) / (x - y + zz))
assert sp.expand((x**2 - 2*x + 2)*(x**2 + 2*x + 2) - (x**4 + 4)) == 0
assert sp.expand(x**2 + 2*x + 2 - ((x + 1)**2 + 1)) == 0
same((x**4 + 4) / (x**2 + 2*x + 2), x**2 - 2*x + 2)
boxed(r"\dfrac{x + y - z}{x - y + z} \text{ với } x + y + z \neq 0,\ x - y + z \neq 0"); boxed(r"x^2 - 2x + 2")

# 030: both methods
aa, bb = sp.symbols("aa bb")
lhs30 = aa / (x - 1) + bb / (x + 1)
coeffs = sp.Poly(sp.expand(aa*(x + 1) + bb*(x - 1) - (5*x + 1)), x).all_coeffs()
assert sp.solve(coeffs, [aa, bb]) == {aa: 3, bb: 2}
assert sp.solve([aa - bb - 1, 3*aa + bb - 11], [aa, bb]) == {aa: 3, bb: 2}
assert (aa*(x + 1) + bb*(x - 1)).subs(x, 0) == aa - bb and (aa*(x + 1) + bb*(x - 1)).subs(x, 2) == 3*aa + bb
same(lhs30.subs({aa: 3, bb: 2}), (5*x + 1) / (x**2 - 1))
assert TEX.count(r"\boxed{a = 3,\ b = 2}") == 2

# 031
b, c = sp.symbols("b c")
n31 = a**3 + b**3 + c**3 - 3*a*b*c
d31 = (a - b)**2 + (b - c)**2 + (c - a)**2
K = a**2 + b**2 + c**2 - a*b - b*c - c*a
assert sp.expand(n31 - (a + b + c)*K) == 0 and sp.expand(d31 - 2*K) == 0
assert sp.expand((a + b)**3 + c**3 - (a + b + c)*(a**2 + 2*a*b + b**2 - a*c - b*c + c**2)) == 0
same(n31 / d31, (a + b + c) / 2)
assert d31.subs({a: 2, b: 2, c: 2}) == 0
boxed(r"\dfrac{a + b + c}{2} \text{ với } a,\ b,\ c \text{ không đồng thời bằng nhau}")

N_PROBLEMS, N_BOXED = 31, 31 + 7 + 6 + 6
assert TEX.count(r"\begin{problem}[8DS-PS-") == N_PROBLEMS
assert TEX.count(r"\boxed{") == N_BOXED + 1, TEX.count(r"\boxed{")  # answers + header comment
print(f"8-phan-thuc: all {N_PROBLEMS} problems verified OK")
