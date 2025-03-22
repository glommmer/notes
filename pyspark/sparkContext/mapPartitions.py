import numpy as np
from pyspark.context import SparkContext


sc = SparkContext.getOrCreate()

# 1: 파티션 수 지정
data = sc.parallelize(np.arange(20))
print(data.collect())
# [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
print(data.glom().collect())
# [[0, 1], [2, 3], [4, 5], [6, 7, 8, 9], [10, 11], [12, 13], [14, 15], [16, 17, 18, 19]]

data1 = sc.parallelize(np.arange(20), 4)  # 파티션 수 지정
print(data1.collect())
# [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
print(data1.glom().collect())
# [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9], [10, 11, 12, 13, 14], [15, 16, 17, 18, 19]]

# 2: mapPartitions()
def f(iterator): yield sum(iterator)

x = sc.parallelize(np.arange(10), 2)
y = x.mapPartitions(f)  # mapPartitions() 파티션 수도 위의 설정 값에 영향 받음
print(x.collect())
# [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
print(x.glom().collect())
# [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]
print(y.collect())
# [10, 35]
print(y.glom().collect())
# [[10], [35]]

# 3: mapPartitionsWithIndex()
def f(split_index, iterator): yield split_index

rdd = sc.parallelize([1, 2, 3, 4], 4)
print(rdd.collect())
# [1, 2, 3, 4]
rdd2 = rdd.mapPartitionsWithIndex(f)
print(rdd2.collect())
print(rdd2.sum())
# [0, 1, 2, 3]
# 6

# 4: mapPartitionsWithIndex()
def f(partition_index, iterator): yield partition_index, sum(iterator)

x = sc.parallelize(np.arange(10), 2)
y = x.mapPartitionsWithIndex(f)

print(x.glom().collect())
# [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]

print(y.glom().collect())
# [[(0, 10)], [(1, 35)]]
