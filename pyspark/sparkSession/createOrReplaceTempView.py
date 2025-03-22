# Temporary Views

# In DataFrames, `temporary views` are used to make the DataFrame available to SQL,
# and work with SQL syntax seamlessly.
# A temporary view gives you a name to query from SQL,
# but unlike a table it exists only for the duration of your Spark Session.
# As a result, the temporary view will not carry over when you restart the cluster or switch to a new notebook.
# It also won't show up in the Data button on the menu on the left side of a Databricks notebook
# which provides easy access to databases and tables.
# The statement in the following cells create a temporary view containing the same data.

# - 데이터 프레임을 해당 SQL 세션에서 사용할 수 있게 만드는 것
# - 일시적으로 만들어 놓는 것
# - Spark Session이 끝나면 사라짐

from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

people_df = spark.read.parquet("/path/to/people.parquet")
people_df.createOrReplaceTempView("People10M")

spark.sql(" select * from People10M where first_name = 'Amanda' ")
# Out[24]: DataFrame[registration_dttm: timestamp, id: int, first_name: string, last_name: string, email: string, gender: string, ip_address: string, cc: string, country: string, birthdate: string, salary: double, title: string, comments: string]

display(spark.sql(" select * from People10M where first_name = 'Amanda' "))
