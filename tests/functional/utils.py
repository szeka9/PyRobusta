import socket
import ssl


def test_assert(name, actual, expected):
    print(f"Test {name}: ", end="")
    if actual == expected:
        print("OK")
    else:
        print("Fail")
        raise AssertionError(f"{actual} != {expected}")


def send_request(srv, request):
    is_tls = srv.config.get("tls")
    sock = socket.create_connection(
        (srv.ip, srv.https_port if is_tls else srv.http_port)
    )

    if is_tls:
        # Disable certificate verification due to self-signed cert
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        sock = ctx.wrap_socket(sock, server_hostname=srv.ip)

    try:
        sock.sendall(request)
        response = bytearray()
        while True:
            response_part = sock.recv(1024)
            if not response_part:
                break
            response.extend(response_part)
        return bytes(response)

    finally:
        sock.close()
