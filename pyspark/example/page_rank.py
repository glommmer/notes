from pyspark.context import SparkContext


sc = SparkContext.getOrCreate()

# 1> 각 페이지가 가리키는 대상을 나타내는 리스트
map_link = sc.parallelize(
    [ 
        ["MapR", "Baidu"], 
        ["MapR", "Blogger"], 
        ["Baidu", "MapR"], 
        ["Blogger", "Google"], 
        ["Blogger", "Baidu"], 
        ["Google", "MapR"] 
    ]
)

# 2> source 별 target 리스트 생성
links = map_link.groupByKey()
print(links.collect())
# Output : 
# [('Baidu', <pyspark.resultiterable.ResultIterable object at 0x7f39cb229150>), 
#  ('Google', <pyspark.resultiterable.ResultIterable object at 0x7f39cb229590>), 
#  ('MapR', <pyspark.resultiterable.ResultIterable object at 0x7f39cb2296d0>), 
#  ('Blogger', <pyspark.resultiterable.ResultIterable object at 0x7f39cb229d10>)]

print(list((k, list(v)) for (k, v) in links.collect()))
# Output : 
# [('Baidu', ['MapR']), 
#  ('Google', ['MapR']), 
#  ('MapR', ['Baidu', 'Blogger']), 
#  ('Blogger', ['Google', 'Baidu'])]

# 3> 각 페이지를 1로 init
ranks = links.map(lambda pairs : (pairs[0], 1))
print(ranks.collect())
# Output : 
# [('Baidu', 1), ('Google', 1), ('MapR', 1), ('Blogger', 1)]

# 4> links와 ranks: inner join
# 누구에게 포인팅 되었는지보다, 얼마나 포인팅 되었나가 중요
cvalues = links.join(ranks)

print(cvalues.collect())
# Output : 
# [('Baidu', (<pyspark.resultiterable.ResultIterable at 0x7fd3f996f3d0>, 1)),
#  ('Google', (<pyspark.resultiterable.ResultIterable at 0x7fd3f996fb50>, 1)),
#  ('MapR', (<pyspark.resultiterable.ResultIterable at 0x7fd3f996fe10>, 1)),
#  ('Blogger', (<pyspark.resultiterable.ResultIterable at 0x7fd3f996fd90>, 1))]

print(list((k, list(v)) for (k, v) in cvalues.collect()))
# Output :
# [('Baidu', [<pyspark.resultiterable.ResultIterable at 0x7fd3f99135d0>, 1]),
#  ('Google', [<pyspark.resultiterable.ResultIterable at 0x7fd3f9913510>, 1]),
#  ('MapR', [<pyspark.resultiterable.ResultIterable at 0x7fd3f9913950>, 1]),
#  ('Blogger', [<pyspark.resultiterable.ResultIterable at 0x7fd3f99139d0>, 1])]

print(list((k, (list(v[0]), v[1])) for (k, v) in cvalues.collect()))
# Output : 
# [('Baidu', (['MapR'], 1)),
#  ('Google', (['MapR'], 1)),
#  ('MapR', (['Baidu', 'Blogger'], 1)),
#  ('Blogger', (['Google', 'Baidu'], 1))]


def compute_contribs(urls: list, rank: int) -> iter:
  """Calculates URL contributions to the rank of other URLs."""
  num_urls = len(urls)
  for url in urls:
    yield (url, rank / num_urls)


# 5> 누구에게 포인팅 받았는지는 중요하지 않으므로 url_urls_rank[0]은 불필요
contribs = links.join(ranks).flatMap(
    lambda url_urls_rank : compute_contribs(
        url_urls_rank[1][0], url_urls_rank[1][1]
    )
) 
print(contribs.collect())
# Output : 
# [('MapR', 1.0),
#  ('MapR', 1.0),
#  ('Baidu', 0.5),
#  ('Blogger', 0.5),
#  ('Google', 0.5),
#  ('Baidu', 0.5)]

# 6> 같은 Key를 가진 것들끼리 묶어서 더해주고, Page Rank 공식 적용
new_rank_data = contribs.mapValues(
    lambda mark : (mark, 1)
)
print(new_rank_data.collect())
# Output : 
# [('MapR', (1.0, 1)), ('MapR', (1.0, 1)), ('Baidu', (0.5, 1)), ('Blogger', (0.5, 1)), ('Google', (0.5, 1)), ('Baidu', (0.5, 1))]

new_rank = new_rank_data.reduceByKey(
    lambda x, y : (x[0] + y[0], x[1] + y[1])
)
print(new_rank.collect())
# Output : 
# [('Baidu', (1.0, 2)), ('Google', (0.5, 1)), ('MapR', (2.0, 2)), ('Blogger', (0.5, 1))]

avg_new_rank = new_rank.map(
    lambda x : (x[0], x[1][0] / x[1][1])
)
print(avg_new_rank.collect())
# Output : 
# [('Baidu', 0.5), ('Google', 0.5), ('MapR', 1.0), ('Blogger', 0.5)]

fin_new_rank = avg_new_rank.mapValues(
    lambda rank : 0.15 + 0.85 * rank
)
print(fin_new_rank.collect())
# Output : 
# [('Baidu', 0.575), ('Google', 0.575), ('MapR', 1.0), ('Blogger', 0.575)]