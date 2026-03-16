import uos


def delete_all(path):
    try:
        for name in uos.listdir(path):
            full = path + "/" + name
            try:
                uos.remove(full)
            except OSError:
                delete_all(full)
                uos.rmdir(full)
        uos.rmdir(path)
    except OSError:
        pass


delete_all("/pyrobusta")
