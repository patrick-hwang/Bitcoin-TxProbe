def _addr_host(addr_str):
    if addr_str.startswith("["):
        return addr_str[1:].split("]")[0]
    if ":" in addr_str:
        host, port = addr_str.rsplit(":", 1)
        if port.isdigit():
            return host
    return addr_str

def _matrix_to_string(mat):
    mat_str = ''
    for i in range(len(mat)):
        mat_str += mat[i].__str__()
        if (i < len(mat) - 1):
            mat_str += '\n'
    return mat_str