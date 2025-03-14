from pyspark import SparkConf
from pyspark.context import SparkContext


sc = SparkContext.getOrCreate()

lines = sc.textFile("yesterday.txt")
print(lines.take(2))
# ["Yesterday, all my troubles seemed so far away",
#  "Now it looks as though they're here to stay"]

# 단어 자르기
counts = lines.flatMap(lambda line : line.split(" "))
# 공백 단위로 split
# map을 사용하면 각 line 마다 리스트 생성되므로, flatMap을 사용해서 boundary를 없앰
print(counts.take(3))
# Output : ['Yesterday,', 'all', 'my']

# 자른 각각의 단어에 number ‘1’ value 부여
counts = counts.map(lambda word : (word, 1))
# 각 key에 '1' value 부여한 Tuple 생성
print(counts.take(3))
# Output : [('Yesterday,', 1), ('all', 1), ('my', 1)]

# Key-Value sorting
counts = counts.reduceByKey(lambda x, y : x + y)
print(counts.take(5))
# Output : [('Yesterday,', 1), ('troubles', 1), ('seemed', 1), ('far', 1), ('away', 3)]

# 각 Tuple의 순서를 뒤집음
# sum한 number가 key값이 됨
e = counts.map(lambda pair : (pair[1], pair[0]))
f = e.sortByKey(ascending=False)
print(f.take(5))
# Output : [(12, 'I'), (8, 'to'), (5, 'Now'), (5, ''), (4, 'she')]

# 저장
counts.saveAsTextFile("count")
