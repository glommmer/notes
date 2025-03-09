# Lambda Function
(lambda a : a + 10)(5)
x = lambda a : a + 10
print(x, x(5))

(lambda x, y : x + y)(2, 3)
x = (lambda x, y : x + y)(2, 3)
print(x)

# lambda는 메모리에 남지 않음
high_ord_func = lambda x, func: x + func(x)
print(high_ord_func(2, lambda x: x * x))

# 함수를 설정하면 메모리에 남아있음
def square(x):
    return x * x
print(high_ord_func(2, square))
