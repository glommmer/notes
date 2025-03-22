import numpy as np
from pyspark.context import SparkContext


sc = SparkContext.getOrCreate()
# SparkContext ⇆ ClusterManager ⇆ WorkerNode
# job 분산 → Resource request, Task schedule, Task execute 등

r_data = [np.random.randn() for _ in range(10)]
print(r_data)

# Output : [0.9382476753599269, 0.21792598227516247, 2.417518905693786, -0.30264428107620794, -0.8295483667892648, -0.8373567184706289, -1.7043499027366846, 0.8267597245830749, 0.05614180178833487, 1.6475736630488298]

data = sc.parallelize(r_data)
print('data : ', data)
print('all data : ', data.collect())
print('the first 5 : ', data.take(5))

# Output : data : ParallelCollectionRDD[1] at readRDDFromFile at PythonRDD.scala:274
# Output : all data : [0.9382476753599269, 0.21792598227516247, 2.417518905693786, -0.30264428107620794, -0.8295483667892648, -0.8373567184706289, -1.7043499027366846, 0.8267597245830749, 0.05614180178833487, 1.6475736630488298]
# Output : the first 5 : [0.9382476753599269, 0.21792598227516247, 2.417518905693786, -0.30264428107620794, -0.8295483667892648]

# collect()
data = sc.parallelize(
    [('Amber', 22), ('Alfred', 23), ('Skye', 4), ('Albert', 12), ('Amber', 9)])

print(data)
print(data.collect())

# Output : ParallelCollectionRDD[0] at readRDDFromFile at PythonRDD.scala:274
# Output : [('Amber', 22), ('Alfred', 23), ('Skye', 4), ('Albert', 12), ('Amber', 9)]

# map()
y = data.map(lambda z : (z, 1))
print(y)
print(y.collect())

# PythonRDD[12] at RDD at PythonRDD.scala:53
# [(('Amber', 22), 1), (('Alfred', 23), 1), (('Skye', 4), 1), (('Albert', 12), 1), (('Amber', 9), 1)]

# filter()
x = sc.parallelize([1, 2, 3])
y = x.filter(lambda x : x % 2 == 1)

print(x.collect())
print(y.collect())

# [1, 2, 3]
# [1, 3]

# map vs flatMap
map = x.map(lambda x : (x, x * 100, 42))
print(x.collect())
print(map.collect())
# [1, 2, 3]
# [(1, 100, 42), (2, 200, 42), (3, 300, 42)]

flatmap = x.flatMap(lambda x : (x, x * 100, 42))

print(x.collect())
print(flatmap.collect())

# [1, 2, 3]
# [1, 100, 42, 2, 200, 42, 3, 300, 42]