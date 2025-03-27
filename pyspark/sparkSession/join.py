from pyspark.sql import SparkSession


spark = SparkSession.builder.getOrCreate()

valuesA = [('Pirate',1),('Monkey',2),('Ninja',3), ('Spaghetti',4)]
TableA = spark.createDataFrame(valuesA, ['name', 'id'])

valuesB = [('Rutabaga',1),('Pirate',2),('Ninja',3),('Darth Vader',4)]
TableB = spark.createDataFrame(valuesB, ['name', 'id'])

TableA.show()
TableB.show()

ta = TableA.alias('ta')
tb = TableA.alias('tb')

inner_join = ta.join(tb, ta.name == tb.name)

left_join = ta.join(tb, ta.name == tb.name, how='left')  # Could also use 'left_outer'
# left_join.filter(col('tb.name').isNull()).show()

right_join = ta.join(tb, ta.name == tb.name, how='right')  # Could also use 'right_outer'
# right_join.filter(col('ta.name').isNotNull()).show()

full_outer_join = ta.join(tb, ta.name == tb.name, how='full')  # Could also use 'full_outer'

inner_join = ta.join(tb, ["name"]) 
# column명이 같다면 이렇게도 할 수는 있으나
# 권장되는 방법은 아님
￼