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
# Inner Join
inner_join = ta.join(tb, ta.name == tb.name)
''' 
+------+---+------+---+
|  name| id|  name| id|
+------+---+------+---+
| Ninja|  3| Ninja|  3|
|Pirate|  1|Pirate|  2|
+------+---+------+---+ 
'''
inner_join = ta.join(tb, on = "name")
inner_join = ta.join(tb, ["name"])
''' 
+------+---+---+
|  name| id| id|
+------+---+---+
| Ninja|  3|  3|
|Pirate|  1|  2|
+------+---+---+ 
'''

# Left (Outer) Join
left_join = ta.join(tb, ta.name == tb.name, how = 'left')
''' 
+---------+---+------+----+
|     name| id|  name|  id|
+---------+---+------+----+
|   Monkey|  2|  null|null|
|    Ninja|  3| Ninja|   3|
|   Pirate|  1|Pirate|   2|
|Spaghetti|  4|  null|null|
+---------+---+------+----+ 
'''
left_join = ta.join(tb, on = "name", how = 'left')
left_join = ta.join(tb, ["name"], how = 'left')
''' 
+---------+---+----+
|     name| id|  id|
+---------+---+----+
|   Monkey|  2|null|
|    Ninja|  3|   3|
|   Pirate|  1|   2|
|Spaghetti|  4|null|
+---------+---+----+ 
'''

# Right (Outer) Join
right_join = ta.join(tb, ta.name == tb.name, how = 'right')
''' 
+------+----+-----------+---+
|  name|  id|       name| id|
+------+----+-----------+---+
|  null|null|Darth Vader|  4|
| Ninja|   3|      Ninja|  3|
|Pirate|   1|     Pirate|  2|
|  null|null|   Rutabaga|  1|
+------+----+-----------+---+ 
'''
right_join = ta.join(tb, on = "name", how = 'right')
right_join = ta.join(tb, ["name"], how = 'right')
''' 
+-----------+----+---+
|       name|  id| id|
+-----------+----+---+
|Darth Vader|null|  4|
|      Ninja|   3|  3|
|     Pirate|   1|  2|
|   Rutabaga|null|  1|
+-----------+----+---+ 
'''

# Full Outer Join
full_outer_join = ta.join(tb, ta.name == tb.name, how = 'full')
'''	
+---------+----+-----------+----+
|     name|  id|       name|  id|
+---------+----+-----------+----+
|     null|null|Darth Vader|   4|
|   Monkey|   2|       null|null|
|    Ninja|   3|      Ninja|   3|
|   Pirate|   1|     Pirate|   2|
|     null|null|   Rutabaga|   1|
|Spaghetti|   4|       null|null|
+---------+----+-----------+----+ 
'''
full_outer_join = ta.join(tb, on = "name", how = 'full')
full_outer_join = ta.join(tb, ["name"], how = 'full')
'''	
+-----------+----+----+
|       name|  id|  id|
+-----------+----+----+
|Darth Vader|null|   4|
|     Monkey|   2|null|
|      Ninja|   3|   3|
|     Pirate|   1|   2|
|   Rutabaga|null|   1|
|  Spaghetti|   4|null|
+-----------+----+----+ 
'''
