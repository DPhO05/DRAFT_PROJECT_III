"""Re-derive every boxed answer in 8-phuong-trinh-bac-nhat-2.tex with sympy."""
import re
from pathlib import Path

import sympy as sp

TEX = (Path(__file__).resolve().parents[1] / "bank-mo-rong" / "8-phuong-trinh-bac-nhat-2.tex").read_text()
x, m, a, b, t = sp.symbols("x m a b t")
R = sp.Rational
checked = []


def boxed(s):
    assert "\\boxed{" + s + "}" in TEX, f"boxed text not in tex: {s}"
    checked.append(s)


def all_boxed(src):
    """Contents of every \\boxed{...} outside comment lines (brace matching)."""
    src = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("%"))
    out = []
    for mt in re.finditer(r"\\boxed\{", src):
        i, depth = mt.end(), 1
        while depth:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        out.append(src[mt.end(): i - 1])
    return out


def sol(lhs, rhs, var=x):
    return set(sp.solve(sp.Eq(lhs, rhs), var))


# 032
assert sol(5*x + 35, 0) == {-7} and sol(8 - 3*x, x - 4) == {3}
boxed(r"x = -7"); boxed(r"x = 3")

# 033
f33 = lambda v: 2*v + 3 - 11
assert [v for v in (-3, 0, 4) if f33(v) == 0] == [4]
assert 3*(-2 + 1) == -2 - 1 and sol(3*(x + 1), x - 1) == {-2}
boxed(r"x = 4"); boxed(r"\text{Có, } x = -2 \text{ là nghiệm}")

# 034
assert sol(3*(2*x - 1) - 2*(x + 4), 5) == {4} and 3*7 - 2*8 == 5
assert sol((x + 1) / 2, (2*x - 3) / 3) == {9}
boxed(r"x = 4"); boxed(r"x = 9")

# 035
e35 = (m + 2)*x - 5 - (3*x + m)
assert sp.expand(e35 - ((m - 1)*x - (m + 5))) == 0
assert sp.solve(sp.Poly(e35, x).coeff_monomial(x), m) == [1]
assert set(sp.solve(e35.subs(x, 2), m)) == {7}
assert set(sp.solve(e35.subs(m, 7), x)) == {2}
boxed(r"m \neq 1"); boxed(r"m = 7")

# 036
assert sol(x + (x - 6), 42) == {24} and 24 - 6 == 18 and 6 < 24 < 42
boxed(r"24 \text{ học sinh nam, } 18 \text{ học sinh nữ}")

# 037
assert sol(R(5, 10)*(x - 3) + R(12, 10), R(2, 10)*x + R(6, 10)) == {3}
assert sol((3*x - 2) / 4, x - 1) == {2}
boxed(r"x = 3"); boxed(r"x = 2")

# 038
assert sol((2*x + 1) / 3 - (x - 1) / 2, x / 6 + 1) == set()
assert sp.expand(2*(2*x + 1) - 3*(x - 1) - (x + 6)) == -1  # 0x = 1
assert sp.expand((x + 3)**2 - x**2 - (3*(2*x + 1) + 6)) == 0  # identity
boxed(r"\text{Phương trình vô nghiệm}"); boxed(r"\text{Phương trình nghiệm đúng với mọi } x")

# 039
assert sol(x / 12 - x / 15, R(20, 60)) == {20} and R(20, 12) - R(20, 15) == R(1, 3)
boxed(r"20 \text{ km}")

# 040
assert sol((3*x + 1) / 4 - 2*(x - 1) / 3, 1 - (x + 2) / 6) == {-1}
assert R(-2, 4) - R(2*(-2), 3) == R(5, 6) == 1 - R(1, 6)
assert sol((x + 3) / 5 - (x - 1) / 2, (7 - x) / 10) == {2}
boxed(r"x = -1"); boxed(r"x = 2")

# 041
assert sol(R(1, 2)*(x + x + 6)*8, 88) == {8} and R(1, 2)*(8 + 14)*8 == 88
boxed(r"\text{Đáy nhỏ } 8 \text{ cm, đáy lớn } 14 \text{ cm}")

# 042
assert sol(x - R(2, 5)*x - 24, x / 5) == {60}
assert R(2, 5)*60 == 24 and 60 - 48 == 12 == R(1, 5)*60
boxed(r"60 \text{ kg}")

# 043
assert sol((2*x - 1)**2 - (2*x + 3)*(2*x - 3), 3*x - 4) == {2}
assert 3**2 - 7*1 == 2 == 3*2 - 4
assert sp.expand((x + 2)**2 - (x - 2)**2) == 8*x and sol((x + 2)**2 - (x - 2)**2, 8*x + 5) == set()
boxed(r"x = 2"); boxed(r"\text{Phương trình vô nghiệm}")

# 044
assert sol(4*x - 8, 2*(x + 7)) == {11} and 4*11 - 15 == 29
assert (11 - 5, 4*(11 - 5)) == (6, 24) and (11 + 7, 29 + 7) == (18, 36) and 36 == 2*18
boxed(r"\text{Con } 11 \text{ tuổi, bố } 29 \text{ tuổi}")

# 045
assert sol(20 + R(4, 10)*x, R(25, 100)*(200 + x)) == {200}
assert sol(2000 + 40*x, 25*(200 + x)) == {200} and R(20 + 80, 400) == R(1, 4)
boxed(r"200 \text{ g}")

# 046
assert sol(3*x - 2, x + 4) == {3}
e46 = lambda mm: sp.Eq(mm*x - 3, x + mm)
assert set(sp.solve(e46(m).subs(x, 3), m)) == {3}
assert sp.solve(e46(3), x) == [3]  # same solution set as (1)
assert sp.expand((m*x - 3 - x - m) - ((m - 1)*x - (m + 3))) == 0
assert e46(1) == sp.false  # 0x = 4: no solution
assert all(sp.solve(e46(mm), x) for mm in range(-20, 21) if mm != 1)
boxed(r"x = 3"); boxed(r"m = 3"); boxed(r"m = 1")

# 047
assert sol(t*(R(1, 6) + R(1, 4)) - (t - 1)*R(1, 12), 1, t) == {R(11, 4)}
assert R(1, 6) + R(1, 4) == R(5, 12) < 1 and R(11, 4) > 1
assert 1 + R(7, 12) / (R(5, 12) - R(1, 12)) == R(11, 4) and R(11, 4) == 2 + R(45, 60)  # 8h45
boxed(r"8 \text{ giờ } 45 \text{ phút}")

# 048
e48 = a*(x - 1) + b*(x + 2) - (5*x + 1)
assert sp.expand(e48 - ((a + b - 5)*x - (a - 2*b + 1))) == 0
assert sp.solve(e48.subs({a: 1, b: 2}), x) == [1]
assert sp.solve([a + b - 5, a - 2*b + 1], [a, b]) == {a: 3, b: 2}
assert sp.expand(e48.subs({a: 3, b: 2})) == 0  # identity
e48c = e48.subs(b, 1)
assert sp.expand(e48c.subs(a, 4)) == -3  # 0x = 3: no solution
assert all(sp.solve(e48c.subs(a, av), x) for av in range(-20, 21) if av != 4)
boxed(r"x = 1"); boxed(r"a = 3,\ b = 2"); boxed(r"a = 4")

# 049
mr = sp.Symbol("mr", real=True)
assert sp.simplify(sp.solve((mr**2 + 1)*x - mr, x)[0] - mr / (mr**2 + 1)) == 0
assert sp.expand(mr**2 + 1 - 1) == mr**2  # m^2 + 1 >= 1 > 0
assert sp.simplify(R(1, 2) - mr / (mr**2 + 1) - (mr - 1)**2 / (2*(mr**2 + 1))) == 0
assert set(sp.solve(mr / (mr**2 + 1) - R(2, 5), mr)) == {2, R(1, 2)}
assert sp.expand(2*m**2 - 4*m - m + 2 - (m - 2)*(2*m - 1)) == 0
assert R(2, 2**2 + 1) == R(2, 5) and R(1, 2) / (R(1, 4) + 1) == R(2, 5)
boxed(r"\text{Vì } m^2 + 1 \geq 1 > 0 \text{ nên phương trình luôn có nghiệm duy nhất } x = \dfrac{m}{m^2 + 1}")
boxed(r"\dfrac{1}{2} - x = \dfrac{(m - 1)^2}{2(m^2 + 1)} \geq 0 \text{ nên } x \leq \dfrac{1}{2}")
boxed(r"m = 2 \text{ hoặc } m = \dfrac{1}{2}")

# 050
e50 = sp.Eq((x - a) / b + (x - b) / a, a / b + b / a)
s50 = sp.solve(e50, x)
assert len(s50) == 1 and sp.simplify(s50[0] - 2*(a**2 + b**2) / (a + b)) == 0
assert s50[0].subs({a: 1, b: 3}) == 5
assert R(5 - 1, 3) + R(5 - 3, 1) == R(10, 3) == R(1, 3) + 3
boxed(r"x = \dfrac{2(a^2 + b^2)}{a + b}"); boxed(r"x = 5")

# 051
e51 = (x - 1) / 99 + (x - 2) / 98 + (x - 3) / 97 - 3
assert sp.solve(e51, x) == [100]
assert sp.simplify(e51 - (x - 100)*(R(1, 99) + R(1, 98) + R(1, 97))) == 0
assert R(1, 99) + R(1, 98) + R(1, 97) > 0
boxed(r"x = 100")

assert sorted(all_boxed(TEX)) == sorted(checked), "some \\boxed answer is not verified"
assert len(re.findall(r"\\begin\{problem\}\[8DS-PT1-(\d{3})\]", TEX)) == 20
assert re.findall(r"\\begin\{problem\}\[8DS-PT1-(\d{3})\]", TEX) == [f"{i:03d}" for i in range(32, 52)]
print("8-phuong-trinh-bac-nhat-2: all 20 problems verified OK")
