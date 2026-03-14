import uos

def delete_all(path):
    for name in uos.listdir(path):
        full = path + "/" + name if path != "/" else "/" + name
        try:
            uos.remove(full)
        except OSError:
            delete_all(full)
            uos.rmdir(full)

delete_all("/")