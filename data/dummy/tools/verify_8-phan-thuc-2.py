"""Re-derive every boxed answer in 8-phan-thuc-2.tex with sympy."""
from pathlib import Path

import sympy as sp

TEX = (Path(__file__).resolve().parents[1] / "bank-mo-rong" / "8-phan-thuc-2.tex").read_text()
x, y = sp.symbols("x y")
xr = sp.Symbol("xr", real=True)
R = sp.Rational
CHECKED = set()


def boxed(s):
    assert "\\boxed{" + s + "}" in TEX, f"boxed text not in tex: {s}"
    CHECKED.add(s)


def same(a, b):
    assert sp.simplify(a - b) == 0, (a, b)


def bad(*polys):
    """Real x where any given polynomial (denominator or divisor numerator) vanishes."""
    out = set()
    for p in polys:
        out |= set(sp.solve(sp.Eq(p, 0), x))
    return out


def all_boxed(tex):
    """Every \\boxed{...} body in the problems (header comment excluded), by brace matching."""
    body = tex[tex.index("\\begin{document}"):]
    out, i = [], 0
    while (i := body.find("\\boxed{", i)) != -1:
        j, depth = i + len("\\boxed{"), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(body[j], 0)
            j += 1
        out.append(body[i + len("\\boxed{"):j - 1])
        i = j
    return out


# 032
assert bad(2*x + 6) == {-3}
assert bad(x**2 - 4*x) == {0, 4}
assert sp.solve(xr**2 + 1, xr) == []  # x^2 + 1 never 0
boxed(r"x \neq -3"); boxed(r"x \neq 0 \text{ và } x \neq 4"); boxed(r"\text{xác định với mọi } x")

# 033
X, Y = sp.symbols("X Y", nonzero=True)
assert sp.simplify(14*X**2*Y / (21*X*Y**3) - 2*X / (3*Y**2)) == 0
assert sp.gcd(14, 21) == 7
same((4*x - 8) / (x**2 - 4), 4 / (x + 2))
assert bad(x**2 - 4) == {2, -2}
boxed(r"\dfrac{2x}{3y^2} \text{ với } x \neq 0,\ y \neq 0"); boxed(r"\dfrac{4}{x + 2} \text{ với } x \neq 2,\ x \neq -2")

# 034
same((x + 5) / (x - 3) - (2*x + 2) / (x - 3), -1)
same(1 / x + 2 / (x + 3), 3*(x + 1) / (x*(x + 3)))
assert sp.expand(x + 5 - 2*x - 2) == 3 - x and sp.gcd(3*(x + 1), x*(x + 3)) == 1
assert bad(x - 3) == {3} and bad(x, x + 3) == {0, -3}
boxed(r"-1 \text{ với } x \neq 3"); boxed(r"\dfrac{3(x + 1)}{x(x + 3)} \text{ với } x \neq 0,\ x \neq -3")

# 035
same(((x**2 - 9) / (x + 1)) / ((x + 3) / (3*x + 3)), 3*(x - 3))
assert bad(x + 1, 3*x + 3, x + 3) == {-1, -3}  # x + 3: divisor numerator
boxed(r"3(x - 3) \text{ với } x \neq -1,\ x \neq -3")

# 036
A36 = sp.cancel((x + 4)*(x**2 - 16) / (x**2 + 8*x + 16))
assert sp.expand(A36 - (x - 4)) == 0
assert sp.expand(x**2 + 8*x + 16 - (x + 4)**2) == 0
same((x - 4) / (x + 4), (x**2 - 16) / (x**2 + 8*x + 16))
B36 = sp.cancel((x**2 - 5*x)*(x + 2) / x)
assert sp.expand(B36 - (x**2 - 3*x - 10)) == 0 and sp.expand((x - 5)*(x + 2) - (x**2 - 3*x - 10)) == 0
same((x**2 - 5*x) / (x**2 - 3*x - 10), x / (x + 2))
boxed(r"A = x - 4"); boxed(r"B = x^2 - 3x - 10")

# 037
same((x**2 - 5*x) / (25 - x**2), -x / (x + 5))
assert bad(25 - x**2) == {5, -5}
a, b, c = sp.symbols("a b c")
same((2*a**2 - 2*a*b) / (3*b - 3*a), -2*a / 3)
assert sp.solve(3*b - 3*a, b) == [a]  # denominator zero iff a = b
boxed(r"-\dfrac{x}{x + 5} \text{ với } x \neq 5,\ x \neq -5"); boxed(r"-\dfrac{2a}{3} \text{ với } a \neq b")

# 038
A38 = (x**2 + 2*x + 1) / (x**2 - 1)
same(A38, (x + 1) / (x - 1))
assert bad(x**2 - 1) == {1, -1}
assert A38.subs(x, 3) == 2 and (x**2 - 1).subs(x, -1) == 0 and ((x + 1) / (x - 1)).subs(x, -1) == 0
boxed(r"A = \dfrac{x + 1}{x - 1} \text{ với } x \neq 1,\ x \neq -1"); boxed(r"A = 2 \text{ tại } x = 3;\ A \text{ không xác định tại } x = -1")

# 039
same(x / (x - 3) + x / (x + 3) + 18 / (9 - x**2), 2)
assert bad(x - 3, x + 3, 9 - x**2) == {3, -3}
assert sp.expand(x*(x + 3) + x*(x - 3) - 18 - 2*(x - 3)*(x + 3)) == 0
boxed(r"2 \text{ với } x \neq 3,\ x \neq -3")

# 040
both = 1 / x + 1 / (x + 3)
same(both, (2*x + 3) / (x*(x + 3)))
T40 = 1 / both
same(T40, x*(x + 3) / (2*x + 3))
assert T40.subs(x, 3) == 2 and R(1, 3) + R(1, 6) == R(1, 2) and 1 / R(1, 2) == 2
boxed(r"\dfrac{2x + 3}{x(x + 3)} \text{ (bể)}"); boxed(r"T = \dfrac{x(x + 3)}{2x + 3} \text{ (giờ)}"); boxed(r"2 \text{ giờ}")

# 041
inner = a / (a - b) - b / (a + b)
same(inner, (a**2 + b**2) / (a**2 - b**2))
same(inner / ((a**2 + b**2) / (a**2 - b**2)), 1)
assert sp.expand(a*(a + b) - b*(a - b) - (a**2 + b**2)) == 0
ar, br = sp.symbols("ar br", real=True)
assert sp.solve([ar**2 + br**2, ar - br], [ar, br], dict=True) == [{ar: 0, br: 0}]  # a^2 + b^2 = 0 and a != b impossible
boxed(r"\left(\dfrac{a}{a - b} - \dfrac{b}{a + b}\right) : \dfrac{a^2 + b^2}{a^2 - b^2} = 1")

# 042
P42 = (2*x + 5) / (x + 1)
same(P42, 2 + 3 / (x + 1))
assert bad(x + 1) == {-1}
ints = {k for k in range(-1000, 1001) if k != -1 and R(2*k + 5, k + 1).is_integer}
assert ints == {-4, -2, 0, 2}, ints
assert [R(2*k + 5, k + 1) for k in (-4, -2, 0, 2)] == [1, -1, 5, 3]
boxed(r"x \neq -1"); boxed(r"x \in \{-4;\ -2;\ 0;\ 2\}")

# 043
n43, d43 = x**3 - 4*x, x**3 + 2*x**2 - 4*x - 8
assert sp.factor(n43) == sp.factor(x*(x - 2)*(x + 2))
assert sp.expand(d43 - (x + 2)*(x**2 - 4)) == 0 and sp.expand((x + 2)*(x**2 - 4) - (x - 2)*(x + 2)**2) == 0
same(n43 / d43, x / (x + 2))
assert bad(d43) == {2, -2}
boxed(r"\dfrac{x}{x + 2} \text{ với } x \neq 2,\ x \neq -2")

# 044
cost = (40*x + 1200) / x
same(cost, 40*(x + 30) / x)
assert cost.subs(x, 100) == 52
assert sp.solve(sp.Eq(cost, 70), x) == [40] and R(40*40 + 1200, 40) == 70
boxed(r"\dfrac{40(x + 30)}{x} \text{ (nghìn đồng)}"); boxed(r"52 \text{ nghìn đồng}"); boxed(r"40 \text{ sản phẩm}")

# 045
inner45 = 3 / (x - 1) - (x + 5) / (x**2 - 1)
same(inner45, 2 / (x + 1))
P45 = inner45 / ((2*x - 1) / (x + 1))
same(P45, 2 / (2*x - 1))
excl45 = bad(x - 1, x**2 - 1, x + 1, 2*x - 1)  # 2x - 1: divisor numerator
assert excl45 == {1, -1, R(1, 2)}
cand = set(sp.solve(sp.Eq(sp.Abs(xr - 1), 2), xr))
assert cand == {3, -1} and cand - excl45 == {3} and P45.subs(x, 3) == R(2, 5)
ints = {k for k in range(-1000, 1001) if k not in excl45 and R(2, 2*k - 1).is_integer}
assert ints == {0}, ints
assert inner45.subs(x, 0) / ((2*0 - 1) / R(1)) == -2 or ((3 / R(-1) - R(5, -1)) / R(-1, 1)) == -2
assert R(2, 2*0 - 1) == -2
boxed(r"P = \dfrac{2}{2x - 1} \text{ với } x \neq 1,\ x \neq -1,\ x \neq \dfrac{1}{2}"); boxed(r"P = \dfrac{2}{5}"); boxed(r"x = 0")

# 046
xp = sp.Symbol("xp", positive=True)
D = (xp**2 + 16) / xp
same(D - 8, (xp - 4)**2 / xp)
assert sp.solve(sp.diff(D, xp), xp) == [4] and D.subs(xp, 4) == 8
assert sp.minimum(D, xp, sp.Interval.open(0, sp.oo)) == 8
boxed(r"\min D = 8 \text{ khi } x = 4")

# 047
assert sp.expand((x + 1 / x)**2 - (x**2 + 2 + 1 / x**2)) == 0
same(x**2 / (x**4 + x**2 + 1), 1 / (x**2 + 1 + 1 / x**2))
roots47 = sp.solve(x**2 - 3*x + 1, x)
assert len(roots47) == 2
for t in roots47:
    assert sp.simplify(t + 1/t - 3) == 0
    assert sp.simplify(t**2 + 1/t**2) == 7
    assert sp.simplify(t**2 / (t**4 + t**2 + 1)) == R(1, 8)
boxed(r"A = 7"); boxed(r"B = \dfrac{1}{8}")

# 048
assert sp.factor(x**2 - 3*x + 2) == (x - 1)*(x - 2)
aa, bb = sp.symbols("aa bb")
cross = sp.expand((x**2 + aa*x + bb)*(x - 2) - (x**2 - 3*x + 2)*(x + 3))
assert sp.solve(sp.Poly(cross, x).all_coeffs(), [aa, bb]) == {aa: 2, bb: -3}
assert sp.expand((x - 1)*(x + 3) - (x**2 + 2*x - 3)) == 0
same((x**2 + 2*x - 3) / (x**2 - 3*x + 2), (x + 3) / (x - 2))
boxed(r"a = 2,\ b = -3")

# 049
T49 = 60 / x + 60 / (x - 10)
same(T49, 120*(x - 5) / (x*(x - 10)))
v49 = 120 / T49
same(v49, x*(x - 10) / (x - 5))
assert v49.subs(x, 30) == 24 and R(60, 30) + R(60, 20) == 5 and R(120, 5) == 24
boxed(r"T = \dfrac{120(x - 5)}{x(x - 10)} \text{ (giờ)}"); boxed(r"v = \dfrac{x(x - 10)}{x - 5} \text{ (km/h)}"); boxed(r"24 \text{ km/h}")

# 050
T50 = b*c / a**2 + c*a / b**2 + a*b / c**2
cond = 1 / a + 1 / b + 1 / c
assert sp.simplify(cond - (a*b + b*c + c*a) / (a*b*c)) == 0
(csol,) = sp.solve(sp.Eq(cond, 0), c)
assert sp.simplify(T50.subs(c, csol)) == 3
assert sp.simplify(T50 - (a**3*b**3 + b**3*c**3 + c**3*a**3) / (a**2*b**2*c**2)) == 0
p, q, r = sp.symbols("p q r")
assert sp.expand((p + q)**3 - 3*p*q*(p + q) - (p**3 + q**3)) == 0
assert sp.expand(p**3 + q**3 + r**3 - 3*p*q*r - (p + q + r)*(p**2 + q**2 + r**2 - p*q - q*r - r*p)) == 0
assert T50.subs({a: 1, b: 1, c: R(-1, 2)}) == 3 and cond.subs({a: 1, b: 1, c: R(-1, 2)}) == 0
boxed(r"T = 3")

# 051
M = (1 / (x - 2) - 1 / (x + 2)) * (x**2 - 4) / (x**2 + 2*x + 5)
same(1 / (x - 2) - 1 / (x + 2), 4 / (x**2 - 4))
same(M, 4 / (x**2 + 2*x + 5))
assert bad(x - 2, x + 2) == {2, -2} and sp.solve(xr**2 + 2*xr + 5, xr) == []
assert sp.expand(x**2 + 2*x + 5 - ((x + 1)**2 + 4)) == 0
cand = set(sp.solve(sp.Eq(4 / (x**2 + 2*x + 5), R(4, 5)), x))
assert cand == {0, -2} and cand - {2, -2} == {0} and M.subs(x, 0) == R(4, 5)
assert sp.maximum(4 / (xr**2 + 2*xr + 5), xr, sp.S.Reals) == 1 and M.subs(x, -1) == 1
boxed(r"M = \dfrac{4}{x^2 + 2x + 5} \text{ với } x \neq 2,\ x \neq -2"); boxed(r"x = 0"); boxed(r"\max M = 1 \text{ khi } x = -1")

N_PROBLEMS = 20
assert TEX.count(r"\begin{problem}[8DS-PS-0") == N_PROBLEMS
for k in range(32, 52):
    assert TEX.count(f"\\begin{{problem}}[8DS-PS-{k:03d}]") == 1, k
assert set(all_boxed(TEX)) == CHECKED, set(all_boxed(TEX)) ^ CHECKED  # every boxed answer was verified
print(f"8-phan-thuc-2: all {N_PROBLEMS} problems verified OK")
