from gc import mem_free, mem_alloc, collect

from protocol.web import WebEngine

def mem_usage(*_):
    collect()
    free = mem_free()
    used = mem_alloc()
    usage_percentage = 100 * used / (free + used)
    return 'text/plain', (
        f"Currently used: {usage_percentage:.2f}%\n"
        f"Free   [bytes]: {free}\n"
        f"Used   [bytes]: {used}\n"
        f"Total  [bytes]: {used + free}\n"
    )

def load():
    WebEngine.register('mem-usage', mem_usage)
    print(f"[mem_usage] registered endpoints: {WebEngine.ENDPOINTS}")