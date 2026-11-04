"""Re-derive every boxed answer of 9-bat-phuong-trinh-2.tex."""
import random

from sympy import Interval, Rational as R, S, Symbol, expand, oo, simplify, symbols
from sympy.solvers.inequalities import solve_univariate_inequality as sui

x = Symbol("x", real=True)
m = Symbol("m", real=True)
a, b, c, y = symbols("a b c y", real=True)
random.seed(7)


def sol(ineq):
    return sui(ineq, x, relational=False)


# 032: 5-2x >= 1 -> x <= 2 ; among -3, 0, 2, 5 -> -3, 0, 2
assert sol(5 - 2 * x >= 1) == Interval(-oo, 2)
assert [v for v in (-3, 0, 2, 5) if 5 - 2 * v >= 1] == [-3, 0, 2]

# 033: m>n => m+5>n+5 ; -3m<-3n ; 4-m/2 < 4-n/2 (differences signed by m-n>0)
d = Symbol("d", positive=True)  # d = m - n
assert simplify((m + 5) - (m - d + 5)) == d
assert expand(-3 * (m - d) - (-3 * m)) == 3 * d
assert simplify((4 - (m - d) / 2) - (4 - m / 2)) == d / 2

# 034: 4x-7<5 -> x<3 ; -2/3 x + 1 <= 5 -> x >= -6
assert sol(4 * x - 7 < 5) == Interval.open(-oo, 3)
assert sol(-R(2, 3) * x + 1 <= 5) == Interval(-6, oo)
assert -R(2, 3) * -6 + 1 == 5 and not (-R(2, 3) * -9 + 1 <= 5)

# 035: 1<a<3, 2<b<5 -> 3<a+b<8 ; -4<a-b<1 (corners of the box are the sup/inf, both strict)
corners = [(p, q) for p in (1, 3) for q in (2, 5)]
assert min(p + q for p, q in corners) == 3 and max(p + q for p, q in corners) == 8
assert min(p - q for p, q in corners) == -4 and max(p - q for p, q in corners) == 1
for _ in range(2000):
    p, q = random.uniform(1, 3), random.uniform(2, 5)
    assert 3 <= p + q <= 8 and -4 <= p - q <= 1

# 036: 2(x-3)-5(1-x) >= 4x+1 -> x >= 4
assert expand(2 * (x - 3) - 5 * (1 - x)) == 7 * x - 11
assert sol(2 * (x - 3) - 5 * (1 - x) >= 4 * x + 1) == Interval(4, oo)
assert 2 * 1 - 5 * (1 - 4) == 17 == 4 * 4 + 1 and 2 * (3 - 3) - 5 * (1 - 3) == 10

# 037: 78000 + 7000x <= 150000 -> 10 notebooks
assert sol(78000 + 7000 * x <= 150000) == Interval(-oo, R(72, 7))
assert max(k for k in range(0, 100) if 78000 + 7000 * k <= 150000) == 10
assert 78000 + 7000 * 10 == 148000 and 78000 + 7000 * 11 == 155000

# 038: -5 < 2x+1 <= 9 -> -3 < x <= 4 ; 7 integers
s38 = sol(2 * x + 1 > -5).intersect(sol(2 * x + 1 <= 9))
assert s38 == Interval.Lopen(-3, 4)
assert [k for k in range(-50, 50) if k in s38] == [-2, -1, 0, 1, 2, 3, 4]

# 039: (x-3)^2+2x >= (x+4)(x-4)+13 -> x <= 3 ; positive integers 1,2,3
assert expand((x - 3) ** 2 + 2 * x) == x**2 - 4 * x + 9 and expand((x + 4) * (x - 4) + 13) == x**2 - 3
s39 = sol((x - 3) ** 2 + 2 * x >= (x + 4) * (x - 4) + 13)
assert s39 == Interval(-oo, 3)
assert [k for k in range(1, 100) if k in s39] == [1, 2, 3]

# 040: (2x-1)/3 - (x+2)/6 < (3-x)/2 + 1 -> x < 19/6
assert expand(6 * ((2 * x - 1) / 3 - (x + 2) / 6)) == 3 * x - 4 and expand(6 * ((3 - x) / 2 + 1)) == 15 - 3 * x
assert sol((2 * x - 1) / 3 - (x + 2) / 6 < (3 - x) / 2 + 1) == Interval.open(-oo, R(19, 6))

# 041: (6+7+8+2y)/5 >= 7.5, y integer 0..10 -> min 9
assert sol((21 + 2 * x) / 5 >= R(15, 2)) == Interval(R(33, 4), oo)
assert min(k for k in range(0, 11) if R(21 + 2 * k, 5) >= R(15, 2)) == 9
assert R(21 + 18, 5) == R(39, 5) > R(15, 2) > R(21 + 16, 5)

# 042: (x-3)/2 <= x+1 and 4-3x > -2 -> -5 <= x < 2 ; negative integers: 5
s42a, s42b = sol((x - 3) / 2 <= x + 1), sol(4 - 3 * x > -2)
assert s42a == Interval(-5, oo) and s42b == Interval.open(-oo, 2)
assert s42a.intersect(s42b) == Interval.Ropen(-5, 2)
assert [k for k in range(-50, 0) if k in s42a.intersect(s42b)] == [-5, -4, -3, -2, -1]

# 043: a/b+b/a-2 = (a-b)^2/(ab) ; (a+b)(1/a+1/b) = 2 + a/b + b/a >= 4
ap, bp = symbols("ap bp", positive=True)
assert simplify(ap / bp + bp / ap - 2 - (ap - bp) ** 2 / (ap * bp)) == 0
assert simplify((ap + bp) * (1 / ap + 1 / bp) - (2 + ap / bp + bp / ap)) == 0
for _ in range(2000):
    p, q = random.uniform(0.01, 10), random.uniform(0.01, 10)
    assert p / q + q / p >= 2 - 1e-9 and (p + q) * (1 / p + 1 / q) >= 4 - 1e-9
assert R(2, 3) / R(2, 3) * 2 == 2 and (R(2, 3) + R(2, 3)) * (2 / R(2, 3)) == 4

# 044: (3-x)/4 - (2x+1)/3 < 2 -> x > -19/11 -> smallest integer -1
assert expand(12 * ((3 - x) / 4 - (2 * x + 1) / 3)) == 5 - 11 * x
s44 = sol((3 - x) / 4 - (2 * x + 1) / 3 < 2)
assert s44 == Interval.open(R(-19, 11), oo)
assert min(k for k in range(-50, 50) if k in s44) == -1
assert R(3 + 1, 4) - R(-1, 3) == R(4, 3) and R(5, 4) - R(-3, 3) == R(9, 4)

# 045: x^2+y^2+1-(xy+x+y) = ((x-y)^2+(x-1)^2+(y-1)^2)/2 ; equality at x=y=1
x2, y2 = symbols("x2 y2", real=True)
assert expand(2 * (x2**2 + y2**2 + 1 - (x2 * y2 + x2 + y2)) - ((x2 - y2) ** 2 + (x2 - 1) ** 2 + (y2 - 1) ** 2)) == 0
for _ in range(2000):
    p, q = random.uniform(-10, 10), random.uniform(-10, 10)
    assert p * p + q * q + 1 >= p * q + p + q - 1e-9
assert 1 + 1 + 1 == 1 * 1 + 1 + 1

# 046: (1) 3x-2 > x+4 -> x>3 ; (2) 2x-1<=m -> x <= (m+1)/2 ; exactly 3 common integers <=> 11 <= m < 13
assert sol(3 * x - 2 > x + 4) == Interval.open(3, oo)


def common46(mv):
    return [k for k in range(-50, 50) if 3 * k - 2 > k + 4 and 2 * k - 1 <= mv]


assert all((len(common46(R(n, 4))) == 3) == (11 <= R(n, 4) < 13) for n in range(0, 80))
assert common46(11) == [4, 5, 6] and len(common46(13)) == 4 and common46(10) == [4, 5]
assert sui(6 <= (m + 1) / 2, m, relational=False).intersect(sui((m + 1) / 2 < 7, m, relational=False)) == Interval.Ropen(11, 13)

# 047: 20 boxes of 30/50 kg, total in [700, 800] -> 5..10 boxes of type II
assert expand(30 * (20 - x) + 50 * x) == 20 * x + 600
assert [k for k in range(0, 21) if 700 <= 30 * (20 - k) + 50 * k <= 800] == [5, 6, 7, 8, 9, 10]
assert 600 + 20 * 4 == 680 and 600 + 20 * 11 == 820

# 048: a+b+c=3 -> a^2+b^2+c^2 >= 3 (equality a=b=c=1) ; ab+bc+ca <= 3
a3, b3 = symbols("a3 b3", real=True)
c3 = 3 - a3 - b3
assert expand(a3**2 + b3**2 + c3**2 - 3 - ((a3 - 1) ** 2 + (b3 - 1) ** 2 + (c3 - 1) ** 2)) == 0
assert expand(a3 * b3 + b3 * c3 + c3 * a3 - 3 + ((a3 - 1) ** 2 + (b3 - 1) ** 2 + (c3 - 1) ** 2) / 2) == 0
assert expand((a3 + b3 + c3) ** 2 - (a3**2 + b3**2 + c3**2 + 2 * (a3 * b3 + b3 * c3 + c3 * a3))) == 0
for _ in range(2000):
    p, q = random.uniform(-10, 10), random.uniform(-10, 10)
    r = 3 - p - q
    assert p * p + q * q + r * r >= 3 - 1e-9 and p * q + q * r + r * p <= 3 + 1e-9

# 049: 300 g of 8% salt water, add x g water -> concentration <= 5% -> x >= 180
assert 300 * R(8, 100) == 24
assert sol(R(24) / (300 + x) <= R(5, 100)).intersect(Interval(0, oo)) == Interval(180, oo)
assert R(24, 480) == R(5, 100) and R(24, 479) > R(5, 100)

# 050: (a+b)(b+c)(c+a) - 8abc = a(b-c)^2 + b(c-a)^2 + c(a-b)^2 ; equality iff a=b=c
assert expand((a + b) * (b + c) * (c + a) - 8 * a * b * c - (a * (b - c) ** 2 + b * (c - a) ** 2 + c * (a - b) ** 2)) == 0
assert expand((a + b) * (b + c) * (c + a)) == expand(a**2 * b + a**2 * c + a * b**2 + b**2 * c + b * c**2 + c**2 * a + 2 * a * b * c)
for _ in range(2000):
    p, q, r = (random.uniform(0.01, 10) for _ in range(3))
    assert (p + q) * (q + r) * (r + p) >= 8 * p * q * r - 1e-6
assert (1 + 1) * (1 + 1) * (1 + 1) == 8 * 1

# 051: (x+1)/99 + (x+2)/98 + (x+3)/97 + 3 <= 0 -> x <= -100
f51 = (x + 1) / 99 + (x + 2) / 98 + (x + 3) / 97 + 3
assert simplify(f51 - (x + 100) * (R(1, 99) + R(1, 98) + R(1, 97))) == 0
assert sol(f51 <= 0) == Interval(-oo, -100)
assert f51.subs(x, -100) == 0 and f51.subs(x, 0) > 0

print("BPT-2: all 20 answers verified")
