# Filter Function
# filter(fuction, iterable)

# 1
print(range(-5, 5))
# Output : range(-5, 5)
# 쓰지 않을 수도 있으므로 구태여 space를 잡지 않음
list(range(-5, 5))
# Output : [-5, -4, -3, -2, -1, 0, 1, 2, 3, 4]
# 실제로 사용할 때 출력

# 2
a = filter(lambda x : x < 0, range(-5, 5))
print(list(a))
# Output : [-5, -4, -3, -2, -1]

# 3
a = [1, 2, 3, 5, 7, 9]
b = [2, 3, 5, 6, 7, 8]
list(filter(lambda x : x in a, b))  # a는 lambda에 소속. x에 b를 삽입
# Output : [2, 3, 5, 7]

# 4
ages = [5, 12, 17, 18, 24, 32]

def myFunc(x):
    if x < 18:
        return False
    else:
        return True

adults = filter(myFunc, ages)
list(adults)
# Output : [18, 24, 32]

list(filter(lambda x : x >= 18, ages))
# Output : [18, 24, 32]
# True만 출력

# 5
alphabets = ['a', 'b', 'd', 'e', 'i', 'j', 'o']

def filter_vowels(alphabet):
    vowels = ['a', 'e', 'i', 'o', 'u']

    if(alphabet in vowels):
        return True
    else:
        return False

filtered_vowels = filter(filter_vowels, alphabets)

print('The filtered vowels are:')
for vowel in filtered_vowels:
    print(vowel)

# The filtered vowels are:
# a
# e
# i
# o

# 6
str_obj = 'Hi this is a sample string, a very simple string'

filtered_chars = ''.join((filter(lambda x : x not in ['a', 's'], str_obj)))
print('Filtered Characters : ', filtered_chars)
# Output : Filtered Characters : Hi thi i  mple tring,  very mple tring
