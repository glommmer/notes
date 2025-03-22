from pyspark.context import SparkContext


sc = SparkContext.getOrCreate()

# 1: groupByKey - Key 가 없는 경우
x = sc.parallelize(['John', 'Fred', 'Anna', 'James'])
y = x.groupBy(lambda w : w[0])  # Key 값: 첫 번째 char

print(y)
# PythonRDD[29] at collect at <ipython-input-23-2b5d62dbd9ae>:3

foo = [(k, v) for k, v in y.collect()]
print(foo)
# [('J', <pyspark.resultiterable.ResultIterable at 0x7f83ced63190>),
#  ('F', <pyspark.resultiterable.ResultIterable at 0x7f83ced53590>),
#  ('A', <pyspark.resultiterable.ResultIterable at 0x7f83ced534d0>)]

foo = [(k, list(v)) for (k, v) in y.collect()]
print(foo)
# [('J', ['John', 'James']), ('F', ['Fred']), ('A', ['Anna'])]

# 2: groupByKey - Key 가 있는 경우
x = sc.parallelize([('B', 5), ('B', 4), ('A', 3), ('A', 2), ('A', 1)])
y = x.groupByKey()

print(y.collect())
# [('B', <pyspark.resultiterable.ResultIterable object at 0x7f83cedd7610>),
#  ('A', <pyspark.resultiterable.ResultIterable object at 0x7f83cedd7290>)]

print(x.collect())
print(list((k, list(v)) for (k, v) in y.collect()))
# [('B', 5), ('B', 4), ('A', 3), ('A', 2), ('A', 1)]
# [('B', [5, 4]), ('A', [3, 2, 1])]

print(x.collect())
print(list((j[0], list(j[1])) for j in y.collect()))
# [('B', 5), ('B', 4), ('A', 3), ('A', 2), ('A', 1)]
# [('B', [5, 4]), ('A', [3, 2, 1])]

# 3: reduceByKey & groupByKey
words = ["one", "two", "two", "three", "three", "three"]
wordPairsRDD = sc.parallelize(words).map(lambda x : (x, 1))
print(wordPairsRDD.collect())
# [('one', 1), ('two', 1), ('two', 1), ('three', 1), ('three', 1), ('three', 1)]

wordsCountWithReduce = wordPairsRDD.reduceByKey(lambda x, y : x + y).collect()
print(wordsCountWithReduce)
# [('two', 2), ('three', 3), ('one', 1)]

wordsCountWithGroup = wordPairsRDD.groupByKey().map(lambda x : (x[0], sum(x[1]))).collect()
print(wordsCountWithGroup)
# [('two', 2), ('three', 3), ('one', 1)]
