from pyspark.sql import Row, SparkSession
from pyspark.context import SparkContext

sc = SparkContext.getOrCreate()
spark = SparkSession.builder.getOrCreate()

# Creare DataFrame from list
# I am following these steps for creating a DataFrame from list of tuples:

# Create a list of tuples. Each tuple contains name of a person with age.
l = [('Ankit', 25), ('Jalfaizy', 22), ('saurabh', 20), ('Bala', 26)]

# Create a RDD from the list above.
rdd = sc.parallelize(l)

# Convert each tuple to a row.
people = rdd.map(lambda x : Row(name=x[0], age=int(x[1])))  # map function으로 Row 생성

# Create a DataFrame by applying createData Frame on RDD with the help of sqIContext.
schema_people = spark.createDataFrame(people)

print(type(schema_people))
# Output : <class 'pyspark.sql.dataframe.DataFrame'>

schema_people.printSchema()
# Output :
# root
#  |-- name: string (nullable = true)
#  |-- age: long (nullable = true)

print(schema_people.collect())
# Output : [Row(name='Ankit', age=25), Row(name='Jalfaizy', age=22), Row(name='saurabh', age=20), Row(name='Bala', age=26)]

print(schema_people.count())
# Output : 4

# Create DataFrame from text file
geoip_rdd = sc.textFile('/FileStore/sample_data/geoip.txt')
geoip_rdd1 = geoip_rdd.map(lambda x : x.split(","))
# ,로 스플릿 -> 리스트 생성
# list of list, 2 dimension
geoip_rdd2 = geoip_rdd1.map(lambda x : Row(ip=x[0], code=x[1], country=x[2]))
geoip_df = spark.createDataFrame(geoip_rdd2)
geoip_df.show()
''' 
+---------------+----+------------------+
|             ip|code|           country|
+---------------+----+------------------+
|194.120.126.123|  NL|       Netherlands|
| 94.126.119.173|  FR|            France|
|  193.46.74.166|  RU|Russian Federation|
|  46.235.67.202|  RU|Russian Federation|
| 193.161.193.64|  RU|Russian Federation|
+---------------+----+------------------+ 
'''
