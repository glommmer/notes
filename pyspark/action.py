from pyspark.sql import SparkSession


spark = SparkSession.builder.getOrCreate()

# Construct a DataFrame from parquet file
# parquet이나 json을 읽어 DataFrame 만든 후 활용
people_df = spark.read.parquet("/FileStore/sample_data/userdata1.parquet")

# RDD에서 collect()와 같은 Action
print(people_df.show(5))
print(people_df.head(5))

print(people_df.count())
print(people_df.columns)  # printSchema와 달리 Column만 보고 싶을 때 사용
print(people_df.describe().show(5))

# To subset the columns, we need to use select operation on DataFrame
# We need to pass the columns names separated by commas inside select Operation.
people_df.select('firstName', 'birthDate').show(5)  # 보고 싶은 columns 선택

# The distinct operation can be used here, to calculate the number of distinct rows in a DataFrame
people_df.select('gender').distinct().count()  # Output : 2
