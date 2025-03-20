from pyspark.sql import SparkSession
from pyspark.sql.functions import year, col


spark = SparkSession.builder.getOrCreate()
people_df = spark.read.parquet("/FileStore/sample_data/userdata1.parquet")

people_df.filter(people_df['gender'] == 'F').count()
people_df.filter(people_df.gender == 'F').count()
people_df.filter("gender == 'F'").count()
people_df.filter(year("birthDate") > '1955').count()
people_df.select("firstName").filter("gender='M'" and year("birthDate") > "1960")
people_df.select("firstName", year("birthDate")).filter("gender='M'" and year("birthDate") > "1960")

people_df.groupBy("gender").count().show()
people_df.orderBy("firstName").groupBy("firstName").count().show(5)
people_df.groupBy("firstName").count().orderBy("count", ascending=False).show(5)  # count()로 sort
people_df.groupBy("firstName").count().orderBy("count").show(5)

people_df.groupBy("firstName").count().filter(col("count") > "5430") \
         .orderBy("count", ascending=False).show(6)

# `count()`를 적용하면 count라는 column이 생성되는데, 생성된 count column에 접근하기 위해서는 `col()` 함수를 import하고 적용해야 함
# `col()`에 대한 추가 설명
#    - `when(col("my_col").isNull()).otherwise("other_col")`
#        > my_col 이라는 컬럼이 NULL일 때, other_col이라는 String을 반환함
#        > other_col이라는 컬럼을 반환하려면 `col("other_col")`이라고 써야 함
#    - 함수가 입력자로 column 자체를 요구하는 때가 있기도 하고
#    - string이 아닌 column을 쓰고자 할 때 `col()`을 써야 함
