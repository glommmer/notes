import ast


foo = '''
# A comment.
print(f"""## Hi! ##""")  # The other comment
'''
print(foo)

parsed_str = ast.parse(foo)
print(parsed_str)
print(ast.dump(parsed_str, indent=4))

unparsed_str = ast.unparse(parsed_str)
print(unparsed_str)
