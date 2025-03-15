from pyspark.context import SparkContext


sc = SparkContext.getOrCreate()

# Text file manipulation
text_file = sc.textFile("yesterday.txt")
text_file.count()
# Output: 25

line_lengths = text_file.map(lambda s: len(s))
line_lengths.take(5)
# Output : [45, 43, 26, 0, 43]

total_length = line_lengths.reduce(lambda a, b: a + b)
total_length
# Output : 613

lines = text_file.filter(lambda line: "yesterday" in line)
lines.take(1)
# Output : ['oh, I believe in yesterday', 'Oh, yesterday came suddenly.']

lines.first()
# Output : 'oh, I believe in yesterday'

data1 = text_file.map(lambda l: l.split("e"))
data1.take(3)
# Output : [['Y', 'st', 'rday, all my troubl', 's s', '', 'm', 'd so far away'],
#           ['Now it looks as though th', "y'r", ' h', 'r', ' to stay'],
#           ['oh, I b', 'li', 'v', ' in y', 'st', 'rday']]

# mapValues()
inputrdd = sc.parallelize(
    [["maths", 50], ["maths", 60], ["english", 65], ["english", 85]]
)
inputrdd.collect()
# Output : [['maths', 50], ['maths', 60], ['english', 65], ['english', 85]]

mapped = inputrdd.mapValues(lambda mark: (mark, 1))
mapped.collect()

# value에만 영향을 미치므로
# value값에만 Tuple 생성

# Output : [('maths', (50, 1)),
#           ('maths', (60, 1)),
#           ('english', (65, 1)),
#           ('english', (85, 1))]

reduced = mapped.reduceByKey(lambda x, y: (x[0] + y[0], x[1] + y[1]))
reduced.collect()
# Output : [('maths', (110, 2)), ('english', (150, 2))]

average = reduced.map(lambda x: (x[0], x[1][0] / x[1][1]))
average.collect()

# Output : [('maths', 55.0), ('english', 75.0)]
