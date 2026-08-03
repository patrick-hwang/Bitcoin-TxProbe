RPCARGS = {"rpcport": 48332, "rpcuser": "expuser1", "rpcpassword": "strongpassword1"}
print(list(RPCARGS))

mat = [
    [1,2,3],
    [4,5,6],
    [7,8,9],
]

res = ''
for i in range(3):
    res += mat[i].__str__()
    if (i < 2):
        res += '\n'

print(res)