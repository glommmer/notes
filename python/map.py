# Map Function
# r = map(func, seq)
# Python3부터는 map()은 iterator 리턴
# 값을 보려면 list로 변환 필요
items = [1, 2, 3, 4, 5]

# 1
squared = []
for i in items:
    squared.append(i**2)

# 2
squared = list(map(lambda x: x **2, items))

# 3
def fahrenheit(T):
    return ((float(9) / 5) * T + 32)

def celsius(T):
    return (float(5) / 9) * (T - 32)

temperatures = (36.5, 37, 37.5, 38, 39)

F = map(fahrenheit, temperatures)
C = map(celsius, F)

print(F)
print(list(C))

# 4
chars = ['s', 'k', 'k', 'a', 'v']
converted = list(map(lambda s: str(s).upper(), chars))

print(converted)

# 5
a = [1, 2, 3, 4]
b = [17, 12, 11, 10]
c = [-1, -4, 5, 9]

D = list(map(lambda x, y : x + y, a, b))
E = list(map(lambda x, y, z : x + y + z, a, b, c))
F = list(map(lambda x, y, z : 2.5 * x + 2 * y - z, a, b, c))

print(D)
print(E)
print(F)

# 6: input - internal function
print(pow(3, 5))  # 3의 5승
print(pow(2, 10))  # 2의 10승

list(map(pow, [3, 2], [5, 10]))

# 7: input - list function
def multiply(x):
    return (x * x)

def add(x):
    return (x + x)

funcs = [multiply, add]
for i in range(5):
    value = list(map(lambda x : x(i), funcs))  # lambda x에 list function이 들어감
    print(value)

# 8: input - dictionary
dict = [{'name': 'python', 'points': 10}, {'name': 'java', 'points': 8}]

A = map(lambda x : x['name'], dict)  
# Output : ['python', 'java']
B = map(lambda x : x['point'] * 10, dict)  
# Output : [100, 80]
C = map(lambda x : x['name'] == 'python', dict)
# Output : [True, False]
